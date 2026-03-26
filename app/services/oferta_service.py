"""
services/oferta_service.py — Servicio de negocio principal.

Orquesta el proceso completo de scraping: coordina el scraper
con los repositorios, gestiona el estado global y registra logs.

Patrón usado: Facade.
Oculta la complejidad del proceso (scraper + repositorios + logs)
detrás de una interfaz sencilla que la capa de API puede usar.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from app.repositories.oferta_repo import OfertaRepository
from app.repositories.log_repo    import LogRepository
from app.services                 import scraper

logger = logging.getLogger(__name__)

# ── Estado del scraping en memoria ────────────────────────────────────────────
# Se usa un dict compartido + un Lock para que sea seguro en multihilo.
# Flask puede recibir peticiones mientras el scraping corre en segundo plano.
_estado_scraping = {
    "en_curso":     False,
    "progreso":     "",
    "log_id":       None,
    "iniciado_en":  None,
    "version":      0,     # Se incrementa cada vez que termina un scrape
}
_lock = threading.Lock()

# Instancias únicas de los repositorios (no tienen estado, son reutilizables)
_repo_oferta = OfertaRepository()
_repo_log    = LogRepository()


# ── API pública del servicio ───────────────────────────────────────────────────

def iniciar_scraping() -> bool:
    """
    Lanza el scraping completo en un hilo de fondo.
    Devuelve True si se inició, False si ya había uno en curso.
    """
    with _lock:
        if _estado_scraping["en_curso"]:
            logger.warning("Intento de iniciar scraping mientras ya hay uno en curso")
            return False
        _estado_scraping["en_curso"]    = True
        _estado_scraping["iniciado_en"] = datetime.now().isoformat()

    hilo = threading.Thread(target=_ejecutar_scraping_completo, daemon=True)
    hilo.start()
    logger.info("Hilo de scraping iniciado")
    return True


def obtener_estado() -> dict:
    """
    Devuelve el estado actual del scraping más los contadores de la BD.
    Usado por el frontend para hacer polling cada pocos segundos.
    """
    with _lock:
        estado = dict(_estado_scraping)

    # Añadir contadores de la BD
    try:
        estado["stats"] = _repo_oferta.obtener_estadisticas()
    except Exception as e:
        logger.error("Error al obtener estadísticas: %s", e)
        estado["stats"] = {}

    # Añadir último log
    try:
        estado["ultimo_log"] = _repo_log.obtener_ultimo()
    except Exception as e:
        logger.error("Error al obtener último log: %s", e)
        estado["ultimo_log"] = None

    return estado


# ── Proceso completo de scraping ───────────────────────────────────────────────

def _ejecutar_scraping_completo():
    """
    Ejecuta todas las fases del scraping de forma secuencial.
    Corre en un hilo separado para no bloquear las peticiones HTTP de Flask.
    """
    log_id          = None
    ofertas_guardadas = 0

    try:
        log_id = _repo_log.crear_log()
        with _lock:
            _estado_scraping["log_id"] = log_id

        # ── Fase 1: Lista de procesos abiertos ────────────────────────────────
        _actualizar_progreso(log_id, "Obteniendo lista de procesos abiertos...")
        lista_abiertos = scraper.obtener_procesos_abiertos()

        if not lista_abiertos:
            _registrar_error(log_id, "Sin procesos — la web puede estar caída o ha cambiado su estructura")

        # Marcar todos como inactivos antes de reactivar los que siguen vivos
        _repo_oferta.marcar_todas_inactivas()

        # ── Fase 2: Detalle de cada proceso abierto (concurrente) ──────────────
        # Usamos un ThreadPoolExecutor para procesar varias ofertas en paralelo.
        # MAX_WORKERS controla cuántas peticiones simultáneas hacemos al servidor
        # del Ayuntamiento. 4 es un valor conservador que agiliza el scraping
        # sin saturar el servidor municipal.
        MAX_WORKERS = 4
        total       = len(lista_abiertos)
        completados = 0
        _lock_contador = threading.Lock()

        def _scrape_oferta(item: dict) -> tuple[bool, str]:
            """
            Descarga el detalle de una oferta y la guarda.
            Devuelve (éxito, mensaje_error).
            Diseñada para ejecutarse en hilos paralelos.
            """
            oferta_id = item["oferta_id"]
            try:
                detalle  = scraper.obtener_detalle_oferta(oferta_id)
                anuncios = detalle.pop("anuncios", [])
                # guardar_oferta y reemplazar_anuncios son thread-safe porque
                # cada llamada abre y cierra su propia conexión SQLite
                _repo_oferta.guardar_oferta({
                    **item,
                    **detalle,
                    "es_activa":    1,
                    "ultimo_scrape": datetime.now().isoformat(),
                })
                _repo_oferta.reemplazar_anuncios(oferta_id, anuncios)
                time.sleep(scraper.Config.PAUSA_ENTRE_REQUESTS)
                return True, ""
            except Exception as e:
                return False, f"Oferta {oferta_id} ({item.get('nombre','?')}): {e}"

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futuros = {executor.submit(_scrape_oferta, item): item for item in lista_abiertos}

            for futuro in as_completed(futuros):
                exito, mensaje_error = futuro.result()
                with _lock_contador:
                    completados += 1
                    if exito:
                        ofertas_guardadas += 1
                    else:
                        logger.error(mensaje_error)
                        _registrar_error(log_id, mensaje_error)

                item = futuros[futuro]
                _actualizar_progreso(
                    log_id,
                    f"Procesos abiertos [{completados}/{total}]: {item['nombre']}"
                )

        logger.info("Fase 2 completada: %d/%d ofertas guardadas", ofertas_guardadas, total)

        # ── Fase 3: Cuadros de ofertas anuales ────────────────────────────────
        _actualizar_progreso(log_id, "Obteniendo cuadros de ofertas históricos...")

        try:
            anios_disponibles = scraper.obtener_anios_disponibles()
        except Exception as e:
            mensaje = f"No se pudo obtener la lista de años: {e}"
            logger.error(mensaje, exc_info=True)
            _registrar_error(log_id, mensaje)
            anios_disponibles = []

        for info_anio in anios_disponibles:
            anio = info_anio["anio"]
            _actualizar_progreso(log_id, f"Cuadro de ofertas {anio}...")

            try:
                entradas = scraper.obtener_cuadro_anual(anio)
                for entrada in entradas:
                    _repo_oferta.guardar_oferta_anual(entrada)

                    # Si la entrada tiene ID y aún no tenemos su detalle, lo descargamos
                    if entrada.get("oferta_id") and not _repo_oferta.existe(entrada["oferta_id"]):
                        try:
                            detalle  = scraper.obtener_detalle_oferta(entrada["oferta_id"])
                            anuncios = detalle.pop("anuncios", [])
                            _repo_oferta.guardar_oferta({
                                **detalle,
                                "es_activa":    0,
                                "ultimo_scrape": datetime.now().isoformat(),
                            })
                            _repo_oferta.reemplazar_anuncios(entrada["oferta_id"], anuncios)
                            time.sleep(scraper.Config.PAUSA_ENTRE_REQUESTS)
                        except Exception as e:
                            logger.debug("No se pudo obtener detalle de %s: %s",
                                         entrada["oferta_id"], e)

            except Exception as e:
                mensaje = f"Año {anio}: {e}"
                logger.error(mensaje, exc_info=True)
                _registrar_error(log_id, mensaje)

            time.sleep(scraper.Config.PAUSA_ENTRE_ANIOS)

        # ── Fin ───────────────────────────────────────────────────────────────
        # Invalidar todas las cachés para que las próximas consultas
        # devuelvan datos frescos recién scrapeados
        from app.utils.cache import invalidar_todo
        invalidar_todo()

        _repo_log.finalizar_log(log_id, "completado", ofertas_guardadas)

    except Exception as e:
        # Error inesperado que no fue capturado en las fases anteriores
        logger.critical("Error crítico en scraping: %s", e, exc_info=True)
        if log_id:
            _registrar_error(log_id, f"Error crítico: {e}")
            _repo_log.finalizar_log(log_id, "error", ofertas_guardadas)

    finally:
        # Siempre liberamos el estado, haya ido bien o mal
        with _lock:
            _estado_scraping["en_curso"]  = False
            _estado_scraping["progreso"]  = ""
            _estado_scraping["version"]  += 1

        logger.info("Scraping finalizado. Versión: %d. Guardadas: %d",
                    _estado_scraping["version"], ofertas_guardadas)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _actualizar_progreso(log_id: Optional[int], mensaje: str):
    """Actualiza el progreso tanto en memoria como en la base de datos."""
    with _lock:
        _estado_scraping["progreso"] = mensaje
    if log_id:
        _repo_log.actualizar_progreso(log_id, mensaje)
    logger.info("Progreso: %s", mensaje)


def _registrar_error(log_id: Optional[int], mensaje: str):
    """Registra un error tanto en el log de Python como en la base de datos."""
    if log_id:
        _repo_log.añadir_error(log_id, mensaje)
