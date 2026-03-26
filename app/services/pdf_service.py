"""
services/pdf_service.py — Servicio de lectura de PDFs de convocatorias.

Las bases de cada convocatoria están publicadas en PDF (BOPZ).
Este servicio descarga el PDF y extrae la información más útil:
  - Temario (lista de temas numerados)
  - Criterios de puntuación / baremo
  - Requisitos de participación
  - Fechas relevantes mencionadas en el texto

Librería usada: pdfplumber
  - Más precisa que pypdf para PDFs con texto real (no escaneados)
  - Extrae tablas además de texto plano
  - Los PDFs del BOPZ tienen texto seleccionable, así que funciona bien

Limitación conocida: los PDFs escaneados (imágenes) no se pueden leer
con esta técnica; necesitarían OCR (pytesseract), que no instalamos
porque requiere Tesseract en el sistema operativo.
"""

import io
import logging
import re
import tempfile
from typing import Optional

import pdfplumber
import requests

from app.config import Config

logger = logging.getLogger(__name__)


# ── Descarga y lectura del PDF ─────────────────────────────────────────────────

def descargar_y_leer_pdf(url: str) -> Optional[dict]:
    """
    Descarga un PDF desde la URL dada y extrae su contenido estructurado.

    Devuelve un dict con:
        - texto_completo: todo el texto del PDF concatenado
        - paginas:        número de páginas
        - temario:        lista de temas extraídos (puede estar vacía)
        - puntuacion:     información sobre baremo/puntuación (puede ser None)
        - requisitos:     fragmento del texto con requisitos de participación
        - fechas:         fechas mencionadas en el documento

    Devuelve None si no se puede leer el PDF.
    """
    logger.info("Descargando PDF: %s", url)

    try:
        respuesta = requests.get(
            url,
            headers=Config.HEADERS,
            timeout=30,          # PDFs pueden ser grandes, timeout generoso
            stream=True          # Descarga en streaming para no cargar todo en memoria
        )
        respuesta.raise_for_status()

        # Verificar que es realmente un PDF
        content_type = respuesta.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            logger.warning("La URL no parece un PDF (content-type: %s): %s", content_type, url)
            return None

        # Leer el contenido en memoria
        contenido_bytes = respuesta.content
        logger.debug("PDF descargado: %.1f KB", len(contenido_bytes) / 1024)

    except requests.exceptions.Timeout:
        logger.error("Timeout descargando PDF: %s", url)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error descargando PDF %s: %s", url, e)
        return None

    # Extraer texto con pdfplumber
    return _extraer_contenido_pdf(contenido_bytes, url)


def _extraer_contenido_pdf(contenido_bytes: bytes, url: str) -> Optional[dict]:
    """
    Extrae el contenido estructurado de los bytes de un PDF usando pdfplumber.
    """
    try:
        with pdfplumber.open(io.BytesIO(contenido_bytes)) as pdf:
            num_paginas   = len(pdf.pages)
            textos_pagina = []

            for i, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if texto:
                    textos_pagina.append(texto)
                else:
                    logger.debug("Página %d sin texto extraíble (posiblemente imagen)", i + 1)

            texto_completo = "\n".join(textos_pagina)

            if not texto_completo.strip():
                logger.warning("PDF sin texto extraíble (puede ser escaneado): %s", url)
                return {
                    "texto_completo": "",
                    "paginas":        num_paginas,
                    "temario":        [],
                    "puntuacion":     None,
                    "requisitos":     None,
                    "fechas":         [],
                    "advertencia":    "PDF sin texto seleccionable (posiblemente escaneado). No se puede extraer contenido automáticamente.",
                }

        logger.info("PDF leído: %d páginas, %d caracteres", num_paginas, len(texto_completo))

        return {
            "texto_completo": texto_completo,
            "paginas":        num_paginas,
            "temario":        _extraer_temario(texto_completo),
            "puntuacion":     _extraer_puntuacion(texto_completo),
            "requisitos":     _extraer_requisitos(texto_completo),
            "fechas":         _extraer_fechas(texto_completo),
            "advertencia":    None,
        }

    except Exception as e:
        logger.error("Error procesando PDF %s: %s", url, e, exc_info=True)
        return None


# ── Extractores específicos ────────────────────────────────────────────────────

def _extraer_temario(texto: str) -> list[dict]:
    """
    Extrae los temas numerados del temario.

    Los temarios del BOPZ suelen tener este formato:
      "Tema 1. Constitución Española de 1978..."
      "1.- El Estado. Concepto y elementos..."
      "TEMA 1: La Constitución Española..."

    Devuelve lista de {numero, texto}.
    """
    temas = []

    # Patrones habituales en los BOPZ de Zaragoza
    patrones = [
        r"(?:Tema|TEMA)\s+(\d+)[.\s:–-]+(.+?)(?=(?:Tema|TEMA)\s+\d+|$)",
        r"^(\d+)[.)\-–]\s+(.+?)(?=^\d+[.)\-–]|$)",
    ]

    for patron in patrones:
        coincidencias = re.findall(patron, texto, re.MULTILINE | re.IGNORECASE | re.DOTALL)
        if len(coincidencias) >= 3:   # Si encontramos al menos 3 temas, parece válido
            for num, contenido in coincidencias:
                texto_tema = " ".join(contenido.split())   # Normalizar espacios
                if len(texto_tema) > 10:                    # Filtrar falsos positivos cortos
                    temas.append({"numero": int(num), "texto": texto_tema[:300]})
            break   # Usamos el primer patrón que funcione

    if temas:
        logger.debug("Temario extraído: %d temas", len(temas))
    else:
        logger.debug("No se encontró temario estructurado en el PDF")

    return temas


def _extraer_puntuacion(texto: str) -> Optional[str]:
    """
    Extrae el bloque de texto relacionado con la puntuación/baremo.
    Busca secciones que hablen de puntos, fases, oposición y concurso.

    Devuelve el fragmento relevante o None si no se encuentra.
    """
    # Palabras clave que suelen encabezar la sección de puntuación
    palabras_clave = [
        "puntuación", "puntuacion", "baremo", "calificación", "calificacion",
        "fase de oposición", "fase de concurso", "valoración de méritos"
    ]

    lineas = texto.split("\n")

    for i, linea in enumerate(lineas):
        linea_lower = linea.lower()
        if any(clave in linea_lower for clave in palabras_clave):
            # Extraer las siguientes 15 líneas como contexto
            fragmento = "\n".join(lineas[i:i+15])
            fragmento = " ".join(fragmento.split())   # Normalizar espacios
            if len(fragmento) > 50:
                return fragmento[:800]   # Limitar tamaño

    return None


def _extraer_requisitos(texto: str) -> Optional[str]:
    """
    Extrae el bloque de requisitos de participación.
    Suele estar bajo epígrafes como "Requisitos", "Condiciones de admisión", etc.
    """
    palabras_clave = [
        "requisitos", "condiciones de admisión", "condiciones de admision",
        "para participar", "podrán participar", "podran participar",
        "aspirantes deberán", "aspirantes deberan"
    ]

    lineas = texto.split("\n")

    for i, linea in enumerate(lineas):
        linea_lower = linea.lower()
        if any(clave in linea_lower for clave in palabras_clave):
            fragmento = "\n".join(lineas[i:i+20])
            fragmento = " ".join(fragmento.split())
            if len(fragmento) > 50:
                return fragmento[:1000]

    return None


def _extraer_fechas(texto: str) -> list[str]:
    """
    Extrae todas las fechas mencionadas en el texto.
    Útil para detectar fechas de examen, plazos, etc. que aparecen en las bases.
    """
    # Patrón para fechas en formato DD/MM/YYYY o "D de mes de YYYY"
    patron_numerico = r"\b\d{1,2}/\d{1,2}/\d{4}\b"
    patron_texto    = r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4}\b"

    fechas_numericas = re.findall(patron_numerico, texto)
    fechas_texto     = re.findall(patron_texto, texto, re.IGNORECASE)

    todas = list(dict.fromkeys(fechas_numericas + fechas_texto))   # Deduplicar manteniendo orden
    return todas[:20]   # Máximo 20 fechas para no saturar


# ── Cronograma de procesos ─────────────────────────────────────────────────────

# URL del cronograma publicado por el Ayuntamiento
URL_CRONOGRAMA = "https://www.zaragoza.es/cont/paginas/oferta/archivos/cronograma/cronograma.pdf"


def leer_cronograma() -> Optional[dict]:
    """
    Descarga y parsea el PDF del cronograma de procesos selectivos.

    El Ayuntamiento publica periódicamente un PDF con el calendario previsto
    de todos los procesos: fecha de examen, fecha de resolución, etc.
    Información que NO aparece en las fichas individuales.

    Devuelve un dict con:
        - entradas: lista de {proceso, fase, fecha_prevista, observaciones}
        - fecha_actualizacion: cuándo se actualizó el cronograma
        - paginas: número de páginas del PDF
        - advertencia: mensaje si el PDF no se pudo parsear completamente
    """
    logger.info("Leyendo cronograma: %s", URL_CRONOGRAMA)
    contenido_pdf = descargar_y_leer_pdf(URL_CRONOGRAMA)

    if not contenido_pdf:
        return None

    if contenido_pdf.get("advertencia"):
        return contenido_pdf   # PDF escaneado o sin texto

    texto = contenido_pdf.get("texto_completo", "")
    return {
        "paginas":             contenido_pdf["paginas"],
        "entradas":            _parsear_cronograma(texto),
        "fechas_mencionadas":  contenido_pdf["fechas"],
        "advertencia":         None,
    }


def _parsear_cronograma(texto: str) -> list[dict]:
    """
    Intenta extraer las filas de la tabla del cronograma.

    El cronograma tiene un formato de tabla con columnas aproximadas:
        Denominación | Fase | Fecha prevista | Observaciones

    Los PDFs del Ayuntamiento no siempre tienen tablas perfectamente
    estructuradas, así que usamos heurísticas basadas en el texto.
    """
    entradas = []
    lineas   = [l.strip() for l in texto.split("\n") if l.strip()]

    # Patrón: líneas que contienen una fecha (indicador de entrada del cronograma)
    patron_fecha = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}\b")

    i = 0
    while i < len(lineas):
        linea = lineas[i]

        # Si la línea contiene una fecha, puede ser una entrada del cronograma
        if patron_fecha.search(linea):
            # Intentar identificar nombre del proceso en la línea anterior
            nombre = lineas[i-1] if i > 0 and len(lineas[i-1]) > 5 else ""
            fechas = patron_fecha.findall(linea)

            # Detectar la fase del proceso
            linea_lower = linea.lower()
            if any(p in linea_lower for p in ["examen", "oposici", "prueba"]):
                fase = "Examen / Prueba"
            elif any(p in linea_lower for p in ["instancia", "solicitud", "inscripci"]):
                fase = "Presentación instancias"
            elif any(p in linea_lower for p in ["resoluc", "nombr"]):
                fase = "Resolución"
            elif any(p in linea_lower for p in ["lista", "admitid"]):
                fase = "Lista admitidos"
            else:
                fase = "Fase no identificada"

            if fechas:
                entradas.append({
                    "proceso":        nombre.strip(),
                    "fase":           fase,
                    "fechas":         fechas,
                    "texto_completo": linea.strip(),
                })
        i += 1

    logger.info("Cronograma parseado: %d entradas encontradas", len(entradas))
    return entradas
