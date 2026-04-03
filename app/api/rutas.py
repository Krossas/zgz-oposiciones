"""
api/rutas.py — Endpoints REST de la aplicación.

Responsabilidad única: recibir peticiones HTTP, validar parámetros,
llamar al servicio correspondiente y devolver la respuesta JSON.

Estructura de respuestas:
  Éxito:  { "ok": true,  "datos": ... }
  Error:  { "ok": false, "error": "mensaje legible" }

Los errores de validación devuelven HTTP 400.
Los recursos no encontrados devuelven HTTP 404.
Los errores de servidor devuelven HTTP 500.
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.repositories.oferta_repo     import OfertaRepository
from app.repositories.log_repo        import LogRepository
from app.repositories.cronograma_repo import CronogramaRepository
from app.services                     import oferta_service
from app.services                     import scraper as scraper_service
from app.utils.validacion             import (
    ErrorValidacion, validar_anio, validar_grupo, validar_estado,
    validar_busqueda, validar_pagina, validar_por_pagina, validar_oferta_id
)

logger           = logging.getLogger(__name__)
api_bp           = Blueprint("api", __name__, url_prefix="/api")

_repo_oferta     = OfertaRepository()
_repo_log        = LogRepository()
_repo_cronograma = CronogramaRepository()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(datos):
    """Respuesta estándar de éxito."""
    return jsonify({"ok": True, "datos": datos})

def _error(mensaje: str, codigo: int = 500):
    """Respuesta estándar de error con logging automático."""
    nivel = logging.WARNING if codigo < 500 else logging.ERROR
    logger.log(nivel, "API %d: %s", codigo, mensaje)
    return jsonify({"ok": False, "error": mensaje}), codigo


# ── Estado y scraping ──────────────────────────────────────────────────────────

@api_bp.route("/estado")
def estado():
    """Estado actual: si hay scraping en curso, versión de datos, estadísticas."""
    try:
        return _ok(oferta_service.obtener_estado())
    except Exception as e:
        logger.error("Error en /api/estado: %s", e, exc_info=True)
        return _error(str(e))


@api_bp.route("/scraping/iniciar", methods=["POST"])
def iniciar_scraping():
    """Lanza el proceso de scraping completo en segundo plano."""
    iniciado = oferta_service.iniciar_scraping()
    if not iniciado:
        return _error("Ya hay un scraping en curso", 409)
    return _ok({"mensaje": "Scraping iniciado"})


@api_bp.route("/scraping/historial")
def historial_scraping():
    """Historial de los últimos scrapings con estado, duración y errores."""
    try:
        limite = validar_por_pagina(request.args.get("limite", 10), maximo=50)
        return _ok(_repo_log.obtener_historial(limite))
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/scraping/historial: %s", e, exc_info=True)
        return _error(str(e))


# ── Ofertas activas ────────────────────────────────────────────────────────────

@api_bp.route("/activas")
def ofertas_activas():
    """
    Lista de procesos selectivos actualmente abiertos.
    Filtros opcionales: grupo, estado, busqueda.
    """
    try:
        grupo    = validar_grupo(request.args.get("grupo"))
        estado   = validar_estado(request.args.get("estado"))
        busqueda = validar_busqueda(request.args.get("busqueda"))
        return _ok(_repo_oferta.obtener_activas(grupo=grupo, estado=estado, busqueda=busqueda))
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/activas: %s", e, exc_info=True)
        return _error(str(e))


# ── Todas las ofertas ──────────────────────────────────────────────────────────

@api_bp.route("/ofertas")
def todas_las_ofertas():
    """
    Lista paginada de todas las ofertas con filtros opcionales.

    Parámetros GET:
        anio, grupo, estado, busqueda  — filtros (todos opcionales)
        pagina                          — página (por defecto: 1)
        por_pagina                      — resultados por página (por defecto: 100, máx: 200)

    La búsqueda usa FTS5 cuando se proporciona 'busqueda':
        - Insensible a mayúsculas/minúsculas
        - Búsqueda por prefijo: "admin" encuentra "Administrativo"
        - Varios términos: "trabajo social" busca ambas palabras

    Respuesta:
        { items, total, pagina, por_pagina, paginas }
    """
    try:
        anio       = validar_anio(request.args.get("anio"))
        grupo      = validar_grupo(request.args.get("grupo"))
        estado     = validar_estado(request.args.get("estado"))
        busqueda   = validar_busqueda(request.args.get("busqueda"))
        pagina     = validar_pagina(request.args.get("pagina"))
        por_pagina = validar_por_pagina(request.args.get("por_pagina"))

        return _ok(_repo_oferta.obtener_todas(
            anio=anio, grupo=grupo, estado=estado,
            busqueda=busqueda, pagina=pagina, por_pagina=por_pagina
        ))
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/ofertas: %s", e, exc_info=True)
        return _error(str(e))


@api_bp.route("/ofertas/<oferta_id>")
def detalle_oferta(oferta_id: str):
    """Detalle completo de una oferta incluyendo todos sus anuncios."""
    try:
        oferta_id = validar_oferta_id(oferta_id)
        oferta    = _repo_oferta.obtener_por_id(oferta_id)
        if not oferta:
            return _error(f"Oferta {oferta_id} no encontrada", 404)
        return _ok(oferta)
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/ofertas/%s: %s", oferta_id, e, exc_info=True)
        return _error(str(e))


@api_bp.route("/ofertas/<oferta_id>/actualizar", methods=["POST"])
def actualizar_oferta(oferta_id: str):
    """Re-scraping de una ficha concreta sin lanzar el proceso completo."""
    try:
        oferta_id = validar_oferta_id(oferta_id)
        detalle   = scraper_service.obtener_detalle_oferta(oferta_id)
        anuncios  = detalle.pop("anuncios", [])
        existente = _repo_oferta.obtener_por_id(oferta_id) or {}
        _repo_oferta.guardar_oferta({
            **existente, **detalle,
            "ultimo_scrape": datetime.now().isoformat(),
        })
        _repo_oferta.reemplazar_anuncios(oferta_id, anuncios)
        return _ok(_repo_oferta.obtener_por_id(oferta_id))
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error al actualizar oferta %s: %s", oferta_id, e, exc_info=True)
        return _error(str(e))


# ── PDF de bases de convocatoria ──────────────────────────────────────────────

@api_bp.route("/ofertas/<oferta_id>/pdf")
def leer_pdf_oferta(oferta_id: str):
    """
    Descarga y analiza el PDF de las bases de la convocatoria.
    Extrae: temario completo, baremo/puntuación, requisitos y fechas.
    Puede tardar varios segundos según el tamaño del PDF.
    """
    from app.services.pdf_service import descargar_y_leer_pdf

    try:
        oferta_id = validar_oferta_id(oferta_id)
        oferta    = _repo_oferta.obtener_por_id(oferta_id)
        if not oferta:
            return _error(f"Oferta {oferta_id} no encontrada", 404)

        url_bases = oferta.get("bases_url")
        if not url_bases:
            return _error("Esta oferta no tiene URL de bases de convocatoria", 404)

        url_pdf = _resolver_url_pdf(url_bases, oferta_id)
        if not url_pdf:
            return _error("No se encontró el PDF en la página de bases", 404)

        contenido = descargar_y_leer_pdf(url_pdf)
        if not contenido:
            return _error("No se pudo leer el PDF", 500)

        return _ok({"oferta_id": oferta_id, "url_pdf": url_pdf, "contenido": contenido})
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error al leer PDF de oferta %s: %s", oferta_id, e, exc_info=True)
        return _error(str(e))


@api_bp.route("/ofertas/<oferta_id>/descargar-pdf")
def descargar_pdf_oferta(oferta_id: str):
    """
    Resuelve y devuelve la URL directa del PDF para descargar.
    Redirecciona directamente al PDF sin intentar leerlo.
    """
    try:
        oferta_id = validar_oferta_id(oferta_id)
        oferta    = _repo_oferta.obtener_por_id(oferta_id)
        if not oferta:
            return _error(f"Oferta {oferta_id} no encontrada", 404)

        url_bases = oferta.get("bases_url")
        if not url_bases:
            return _error("Esta oferta no tiene URL de bases de convocatoria", 404)

        url_pdf = _resolver_url_pdf(url_bases, oferta_id)
        if not url_pdf:
            return _error("No se encontró el PDF", 404)

        from flask import redirect
        return redirect(url_pdf)
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error al resolver PDF de oferta %s: %s", oferta_id, e, exc_info=True)
        return _error(str(e))


def _resolver_url_pdf(url_bases: str, oferta_id: str):
    """
    Intenta obtener la URL directa al PDF del BOPZ.
    Primero prueba el patrón conocido (bases{ID}.pdf), luego parsea el HTML.
    """
    import requests
    from app.config import Config

    url_directa = f"{Config.BASE_URL}/cont/paginas/oferta/archivos/bases/bases{oferta_id}.pdf"
    try:
        r = requests.head(url_directa, headers=Config.HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            return url_directa
    except Exception:
        pass

    try:
        from app.services.scraper import _get
        soup = _get(url_bases)
        for enlace in soup.find_all("a", href=True):
            href = enlace["href"]
            if href.lower().endswith(".pdf"):
                return Config.BASE_URL + href if not href.startswith("http") else href
    except Exception as e:
        logger.debug("No se pudo parsear página de bases %s: %s", url_bases, e)

    return None


# ── Cuadros anuales ───────────────────────────────────────────────────────────

@api_bp.route("/anuales")
def ofertas_anuales():
    """Cuadro de ofertas filtrado por año (o todos si no se especifica)."""
    try:
        anio = validar_anio(request.args.get("anio"))
        return _ok(_repo_oferta.obtener_anuales(anio))
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/anuales: %s", e, exc_info=True)
        return _error(str(e))


@api_bp.route("/anios")
def anios_disponibles():
    """Lista de años de los que hay datos históricos."""
    try:
        return _ok(_repo_oferta.obtener_anios_disponibles())
    except Exception as e:
        logger.error("Error en /api/anios: %s", e, exc_info=True)
        return _error(str(e))


# ── Frecuencia y estadísticas ─────────────────────────────────────────────────

@api_bp.route("/frecuencia")
def frecuencia():
    """Análisis de frecuencia histórica: cuántas veces y en qué años aparece cada puesto."""
    try:
        return _ok(_repo_oferta.obtener_frecuencia())
    except Exception as e:
        logger.error("Error en /api/frecuencia: %s", e, exc_info=True)
        return _error(str(e))


@api_bp.route("/estadisticas")
def estadisticas():
    """Resumen estadístico global de los datos disponibles."""
    try:
        return _ok(_repo_oferta.obtener_estadisticas())
    except Exception as e:
        logger.error("Error en /api/estadisticas: %s", e, exc_info=True)
        return _error(str(e))


# ── Cronograma ────────────────────────────────────────────────────────────────

@api_bp.route("/cronograma")
def cronograma():
    """
    Calendario previsto de procesos selectivos (fuente: PDF del Ayuntamiento).
    Parámetro opcional: busqueda — filtra por nombre de proceso.
    """
    try:
        busqueda = validar_busqueda(request.args.get("busqueda"))
        datos    = (_repo_cronograma.buscar(busqueda)
                    if busqueda
                    else _repo_cronograma.obtener_todo())
        return _ok({
            "entradas":             datos,
            "ultima_actualizacion": _repo_cronograma.ultima_actualizacion(),
        })
    except ErrorValidacion as e:
        return _error(str(e), 400)
    except Exception as e:
        logger.error("Error en /api/cronograma: %s", e, exc_info=True)
        return _error(str(e))


@api_bp.route("/cronograma/actualizar", methods=["POST"])
def actualizar_cronograma():
    """Descarga y re-parsea el PDF del cronograma del Ayuntamiento."""
    from app.services.pdf_service import leer_cronograma

    try:
        resultado = leer_cronograma()
        if not resultado:
            return _error("No se pudo descargar el cronograma", 500)

        if resultado.get("advertencia"):
            return _ok({"mensaje": resultado["advertencia"], "entradas": 0})

        entradas = resultado.get("entradas", [])
        _repo_cronograma.reemplazar_cronograma(entradas)
        return _ok({
            "mensaje":  f"Cronograma actualizado con {len(entradas)} entradas",
            "entradas": len(entradas),
        })
    except Exception as e:
        logger.error("Error al actualizar cronograma: %s", e, exc_info=True)
        return _error(str(e))


# ── Scheduler ─────────────────────────────────────────────────────────────────

@api_bp.route("/scheduler")
def info_scheduler():
    """Estado del scheduler: si está activo y cuándo es la próxima ejecución."""
    from app.services.scheduler import obtener_info_scheduler
    return _ok(obtener_info_scheduler())
