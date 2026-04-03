"""
services/scraper.py — Servicio de scraping de zaragoza.es

Responsabilidad única: leer las páginas web del Ayuntamiento y extraer
los datos en forma de diccionarios Python. NO sabe nada de base de datos.

Puntos técnicos importantes:
- La web usa codificación ISO-8859-1 (no UTF-8), hay que indicárselo a requests
- El HTML es antiguo (tablas, definition lists) así que el parsing es específico
- Se respetan pausas entre peticiones para no saturar el servidor municipal
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional

import dateparser
from dateparser.search import search_dates
import requests
from bs4 import BeautifulSoup

from app.config import Config

logger = logging.getLogger(__name__)

# URLs base
URL_PROCESOS_ABIERTOS = Config.BASE_URL + "/oferta/abierto.jsp"
URL_DETALLE           = Config.BASE_URL + "/oferta/ofertaDetalle.jsp?id={id}"
URL_CUADRO_ANUAL      = Config.BASE_URL + "/ciudad/oferta/oferta{anio}.htm"
URL_HISTORIAL         = Config.BASE_URL + "/ciudad/oferta/informacion/ofertapersonalpermanente.html"


# ── Funciones de bajo nivel ────────────────────────────────────────────────────

def _get(url: str) -> Optional[BeautifulSoup]:
    """
    Descarga una URL y devuelve el HTML parseado.
    Gestiona errores de red y de HTTP de forma centralizada.
    Devuelve None si hay cualquier problema, para que el llamador decida qué hacer.
    """
    try:
        logger.debug("GET %s", url)
        respuesta = requests.get(
            url,
            headers=Config.HEADERS,
            timeout=Config.REQUEST_TIMEOUT,
            # No seguimos redirecciones automáticamente para detectar cambios de URL
        )
        respuesta.raise_for_status()   # Lanza excepción si HTTP >= 400

        # Forzamos la codificación correcta — requests a veces la detecta mal
        respuesta.encoding = Config.ENCODING

        return BeautifulSoup(respuesta.text, "lxml")

    except requests.exceptions.Timeout:
        logger.error("Timeout al acceder a: %s", url)
        raise
    except requests.exceptions.HTTPError as e:
        logger.error("Error HTTP %s en: %s", e.response.status_code, url)
        raise
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en %s: %s", url, e)
        raise


def _limpiar_texto(texto: Optional[str]) -> Optional[str]:
    """Elimina espacios extra y saltos de línea de un texto."""
    if not texto:
        return None
    return " ".join(texto.split()).strip() or None


# ── Scraping de la lista de procesos abiertos ──────────────────────────────────

def obtener_procesos_abiertos() -> list[dict]:
    """
    Scraping de todas las páginas de /oferta/abierto.jsp (paginada).
    Devuelve una lista con {oferta_id, nombre, grupo, url} por proceso.
    """
    resultados = []
    pagina     = 0

    while True:
        # La primera página no lleva parámetro; las siguientes llevan numpag=N
        url = URL_PROCESOS_ABIERTOS if pagina == 0 else f"{URL_PROCESOS_ABIERTOS}?interinidad=No&numpag={pagina}"

        logger.info("Scraping lista procesos abiertos — página %d: %s", pagina + 1, url)
        soup = _get(url)

        # Buscar la tabla de resultados
        tabla = soup.find("table")
        if not tabla:
            logger.warning("No se encontró tabla en página %d", pagina + 1)
            break

        filas_pagina = 0
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            if len(celdas) < 2:
                continue   # Saltamos cabeceras o filas vacías

            enlace = celdas[0].find("a")
            if not enlace or not enlace.get("href"):
                continue

            href      = enlace["href"]
            id_match  = re.search(r"id=(\d+)", href)
            if not id_match:
                continue

            resultados.append({
                "oferta_id": id_match.group(1),
                "nombre":    _limpiar_texto(enlace.get_text()),
                "grupo":     _limpiar_texto(celdas[1].get_text()),
                "url":       Config.BASE_URL + href if not href.startswith("http") else href,
            })
            filas_pagina += 1

        logger.debug("Página %d: %d filas encontradas", pagina + 1, filas_pagina)

        # Comprobamos si hay página siguiente
        if not soup.find("a", string=re.compile("Siguiente", re.I)):
            break

        pagina += 1
        if pagina > 25:   # Límite de seguridad
            logger.warning("Se alcanzó el límite de 25 páginas, abortando paginación")
            break

        time.sleep(Config.PAUSA_ENTRE_REQUESTS)

    logger.info("Total procesos abiertos encontrados: %d", len(resultados))
    return resultados


# ── Scraping del detalle de una oferta ────────────────────────────────────────

def obtener_detalle_oferta(oferta_id: str) -> dict:
    """
    Scraping de la ficha completa de una oferta (/oferta/ofertaDetalle.jsp?id=N).
    Devuelve un dict con todos los campos y la lista de anuncios.
    """
    url  = URL_DETALLE.format(id=oferta_id)
    soup = _get(url)

    datos = {
        "oferta_id": oferta_id,
        "url":       url,
        "anuncios":  [],
    }

    # ── Nombre (está en el h2 principal) ─────────────────────────────────────
    h2 = soup.find("h2")
    if h2:
        datos["nombre"] = _limpiar_texto(h2.get_text())

    # ── Campos de la ficha (pares dt/dd en una definition list) ───────────────
    # La ficha usa <dl><dt>Etiqueta</dt><dd>Valor</dd></dl>
    for dt in soup.find_all("dt"):
        etiqueta = _limpiar_texto(dt.get_text()).lower().rstrip(":")
        dd       = dt.find_next_sibling("dd")
        if not dd:
            continue
        valor = _limpiar_texto(dd.get_text())

        if "año oferta" in etiqueta or "ao oferta" in etiqueta:
            try:
                datos["anio"] = int(valor)
            except (ValueError, TypeError):
                pass
        elif "turno" == etiqueta:
            datos["turno"] = valor
        elif "plantilla" == etiqueta:
            datos["plantilla"] = valor
        elif "escala" in etiqueta or "cuerpo" in etiqueta:
            datos["escala"] = valor
        elif "grupo" == etiqueta:
            datos["grupo"] = valor
        elif "expediente" in etiqueta:
            datos["expediente"] = valor
        elif "total de plazas" in etiqueta or "n total" in etiqueta:
            datos["plazas"] = valor
        elif "tipo examen" in etiqueta:
            datos["tipo_examen"] = valor
        elif "titulaci" in etiqueta:
            datos["titulacion"] = valor
        elif "observaciones" == etiqueta:
            datos["observaciones"] = valor
        elif "convocatoria b.o.p" in etiqueta:
            datos["convocatoria_bop"] = valor
        elif "convocatoria b.o.e" in etiqueta:
            datos["convocatoria_boe"] = valor
        elif "fecha presentaci" in etiqueta:
            datos["fecha_instancia"] = valor

    # ── Enlace a las bases de la convocatoria ─────────────────────────────────
    enlace_bases = soup.find("a", string=re.compile("Ver Bases", re.I))
    if enlace_bases and enlace_bases.get("href"):
        href = enlace_bases["href"]
        datos["bases_url"] = Config.BASE_URL + href if not href.startswith("http") else href

    # ── Anuncios ───────────────────────────────────────────────────────────────
    # Buscar el h3 "Anuncios" y procesar el bloque siguiente (dl/ul/ol o texto libre)
    anuncios = []
    h3_anuncios = None
    for h3 in soup.find_all("h3"):
        if "anuncio" in h3.get_text().lower():
            h3_anuncios = h3
            break

    def _registrar_anuncio(fecha, texto, url_anuncio=None):
        if texto:
            texto = _limpiar_texto(texto)
            fecha = _limpiar_texto(fecha)
            if fecha and fecha.endswith(":"):
                fecha = fecha[:-1].strip()
            anuncios.append({"fecha": fecha, "texto": texto, "url": url_anuncio or None})

    if h3_anuncios:
        elemento = h3_anuncios.find_next_sibling()
        while elemento:
            if hasattr(elemento, 'name') and elemento.name == 'dl':
                for dt in elemento.find_all('dt'):
                    fecha = None
                    texto = None
                    url_anuncio = None

                    span_fecha = dt.find('span', class_='fecha')
                    if span_fecha:
                        fecha = _limpiar_texto(span_fecha.get_text())

                    a = dt.find('a')
                    if a:
                        texto = _limpiar_texto(a.get_text())
                        url_anuncio = a.get('href', '')
                        if url_anuncio and not url_anuncio.startswith('http'):
                            url_anuncio = Config.BASE_URL + url_anuncio

                    if not texto:
                        raw = _limpiar_texto(dt.get_text())
                        m = re.match(r"^(\d{2}/\d{2}/\d{4}):\s*(.*)$", raw or "")
                        if m:
                            fecha = m.group(1)
                            texto = m.group(2)

                    if texto:
                        _registrar_anuncio(fecha or '', texto, url_anuncio)

            elif hasattr(elemento, 'name') and elemento.name in ('ul', 'ol'):
                for li in elemento.find_all('li'):
                    texto_completo = _limpiar_texto(li.get_text())
                    m = re.match(r"^(\d{2}/\d{2}/\d{4}):\s*(.*)$", texto_completo or "")
                    if m:
                        _registrar_anuncio(m.group(1), m.group(2))

            else:
                # Fallback: intentar extraer del texto completo y de enlaces
                texto_completo = _limpiar_texto(elemento.get_text() if hasattr(elemento, 'get_text') else '')
                # Casos listados en la misma línea con enlaces
                for dt in elemento.find_all('dt') if hasattr(elemento, 'find_all') else []:
                    # procesar si hay dt en un bloque no estándar
                    span_fecha = dt.find('span', class_='fecha')
                    if span_fecha:
                        fecha = _limpiar_texto(span_fecha.get_text())
                        a = dt.find('a')
                        if a:
                            texto = _limpiar_texto(a.get_text())
                            url_anuncio = a.get('href', '')
                            if url_anuncio and not url_anuncio.startswith('http'):
                                url_anuncio = Config.BASE_URL + url_anuncio
                            _registrar_anuncio(fecha or '', texto, url_anuncio)
                if not anuncios:
                    for a in elemento.find_all('a') if hasattr(elemento, 'find_all') else []:
                        href = a.get('href', '')
                        href_full = Config.BASE_URL + href if href and not href.startswith('http') else href
                        texto = _limpiar_texto(a.get_text())
                        # fecha puede aparecer en el mismo bloque de texto completo
                        fecha_match = re.search(r"(\d{2}/\d{2}/\d{4})", texto_completo or "")
                        _registrar_anuncio(fecha_match.group(1) if fecha_match else '', texto, href_full)

            elemento = elemento.find_next_sibling() if hasattr(elemento, 'find_next_sibling') else None

    # Eliminar duplicados exactos dejando primer valor
    visto = set()
    anuncios_unicos = []
    for a in anuncios:
        key = (a.get('fecha'), a.get('texto'), a.get('url'))
        if key not in visto:
            visto.add(key)
            anuncios_unicos.append(a)

    datos['anuncios'] = anuncios_unicos

    datos["anuncios"] = anuncios

    # ── Estado: determinado a partir de los anuncios y fechas ─────────────────
    datos["estado"] = _detectar_estado(datos)

    logger.debug("Detalle obtenido: %s — %s — %d anuncios",
                 oferta_id, datos.get("nombre"), len(anuncios))
    return datos


def _detectar_estado(datos: dict) -> str:
    """
    Infiere el estado del proceso a partir de los datos disponibles.

    Usa dateparser para extraer fechas de los textos de los anuncios,
    lo que permite interpretar tanto "28/12/2025" como "28 de diciembre de 2025".

    Estados posibles:
    - inscripcion_abierta:   El plazo de presentación de instancias está activo hoy
    - pendiente_inscripcion: El plazo aún no ha empezado
    - inscripcion_cerrada:   El plazo terminó pero no hay más movimiento aún
    - en_proceso:            Ya hay listas, tribunal, examen o calificaciones publicadas
    - resuelto:              Hay resolución definitiva o nombramiento
    - bases_publicadas:      Solo se han publicado las bases, nada más
    - pendiente:             No hay anuncios todavía
    """
    from app.config import Config

    anuncios   = datos.get("anuncios") or []
    texto_todo = " ".join(a.get("texto", "").lower() for a in anuncios)
    hoy        = datetime.now().date()

    # Buscar el anuncio de "Presentación de instancias"
    # Usamos dateparser para extraer las fechas — maneja tanto formato numérico
    # (28/12/2025) como en texto (28 de diciembre de 2025)
    for anuncio in anuncios:
        texto = anuncio.get("texto", "")
        if "instancia" not in texto.lower() and "plazo" not in texto.lower():
            continue

        try:
            # Intentar primero con regex (más fiable para fechas en formato DD/MM/YYYY)
            fechas_regex = re.findall(r"(\d{2}/\d{2}/\d{4})", texto)
            if len(fechas_regex) >= 2:
                fecha_inicio = datetime.strptime(fechas_regex[0], "%d/%m/%Y").date()
                fecha_fin    = datetime.strptime(fechas_regex[-1], "%d/%m/%Y").date()
            else:
                # Fallback a dateparser para fechas en texto ("28 de diciembre de 2025")
                fechas_encontradas = search_dates(
                    texto,
                    languages=["es"],
                    settings=Config.DATEPARSER_SETTINGS
                )
                if not fechas_encontradas or len(fechas_encontradas) < 2:
                    continue
                fecha_inicio = fechas_encontradas[0][1].date()
                fecha_fin    = fechas_encontradas[-1][1].date()

            # Sanity check: el fin debe ser posterior al inicio
            if fecha_fin <= fecha_inicio:
                continue

            if fecha_inicio <= hoy <= fecha_fin:
                return "inscripcion_abierta"
            elif hoy < fecha_inicio:
                return "pendiente_inscripcion"
            else:
                indicadores_proceso = [
                    "lista", "admitido", "excluido", "tribunal",
                    "examen", "calificaci", "puntuaci", "prueba"
                ]
                if any(ind in texto_todo for ind in indicadores_proceso):
                    return "en_proceso"
                return "inscripcion_cerrada"
        except Exception as e:
            logger.debug("Error parseando fechas de '%s': %s", texto[:60], e)
            continue

    # Sin plazo de inscripción — inferimos por palabras clave
    if any(p in texto_todo for p in ["resolución definitiv", "nombramiento", "relación definitiv"]):
        return "resuelto"
    if any(p in texto_todo for p in ["tribunal", "examen", "calificaci", "admitido", "prueba"]):
        return "en_proceso"
    if "bases" in texto_todo:
        return "bases_publicadas"
    if anuncios:
        return "inscripcion_cerrada"

    return "pendiente"


# ── Scraping de los cuadros anuales ───────────────────────────────────────────

def obtener_anios_disponibles() -> list[dict]:
    """
    Scraping del historial de cuadros de ofertas para obtener los años disponibles.
    Devuelve [{anio, url, texto}] ordenados de más reciente a más antiguo.
    """
    soup   = _get(URL_HISTORIAL)
    anios  = []
    vistos = set()

    for enlace in soup.find_all("a"):
        href = enlace.get("href", "")
        match = re.search(r"oferta(\d{4})(?:-[^.]+)?\.htm", href)
        if match:
            anio = int(match.group(1))
            if anio not in vistos:
                vistos.add(anio)
                url_completa = Config.BASE_URL + href if not href.startswith("http") else href
                anios.append({"anio": anio, "url": url_completa, "texto": _limpiar_texto(enlace.get_text())})

    anios.sort(key=lambda x: x["anio"], reverse=True)
    logger.info("Años disponibles: %s", [a["anio"] for a in anios])
    return anios


def obtener_cuadro_anual(anio: int) -> list[dict]:
    """
    Scraping del cuadro de ofertas de un año concreto.
    Devuelve una lista de dicts con las plazas previstas para ese año.
    """
    url  = URL_CUADRO_ANUAL.format(anio=anio)
    soup = _get(url)

    tabla    = soup.find("table")
    entradas = []

    if not tabla:
        logger.warning("No se encontró tabla en el cuadro de %d", anio)
        return entradas

    for i, fila in enumerate(tabla.find_all("tr")):
        if i == 0:
            continue   # Saltamos la cabecera

        celdas = fila.find_all("td")
        if len(celdas) < 2:
            continue

        # La primera celda es el nombre, puede tener enlace a la ficha
        enlace    = celdas[0].find("a")
        nombre    = _limpiar_texto(enlace.get_text() if enlace else celdas[0].get_text())
        if not nombre:
            continue

        href      = enlace.get("href", "") if enlace else ""
        oferta_id = None
        url_oferta = None
        id_match  = re.search(r"id=(\d+)", href)
        if id_match:
            oferta_id  = id_match.group(1)
            url_oferta = Config.BASE_URL + href if not href.startswith("http") else href

        entradas.append({
            "anio":          anio,
            "nombre":        nombre,
            "oferta_id":     oferta_id,
            "plazas":        _limpiar_texto(celdas[1].get_text()) if len(celdas) > 1 else None,
            "grupo":         _limpiar_texto(celdas[2].get_text()) if len(celdas) > 2 else None,
            "procedimiento": _limpiar_texto(celdas[3].get_text()) if len(celdas) > 3 else None,
            "titulacion":    _limpiar_texto(celdas[4].get_text()) if len(celdas) > 4 else None,
            "observaciones": _limpiar_texto(celdas[5].get_text()) if len(celdas) > 5 else None,
            "url":           url_oferta,
        })

    logger.info("Cuadro %d: %d entradas", anio, len(entradas))
    return entradas
