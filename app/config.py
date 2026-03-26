"""
config.py — Configuración centralizada de la aplicación.

Todos los parámetros configurables están aquí. Si necesitas cambiar
algo (el puerto, la ruta de la BD, el timeout, la frecuencia del
scraping automático...) solo tocas este fichero.
"""

import os
from pathlib import Path

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).parent.parent

class Config:
    # ── Base de datos ────────────────────────────────────────────────────────
    DB_PATH = BASE_DIR / "datos" / "oposiciones.db"

    # ── Logging ──────────────────────────────────────────────────────────────
    LOG_DIR       = BASE_DIR / "logs"
    LOG_FILE      = LOG_DIR / "app.log"
    LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB por fichero
    LOG_BACKUPS   = 3                  # 3 ficheros de backup
    LOG_LEVEL     = "DEBUG"

    # ── Servidor Flask ───────────────────────────────────────────────────────
    PORT  = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # ── Scraping ─────────────────────────────────────────────────────────────
    BASE_URL              = "https://www.zaragoza.es"
    ENCODING              = "iso-8859-1"
    REQUEST_TIMEOUT       = 15
    PDF_TIMEOUT           = 30      # Los PDFs pueden ser grandes
    PAUSA_ENTRE_REQUESTS  = 0.4
    PAUSA_ENTRE_ANIOS     = 0.6

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # ── Scheduler (scraping automático) ─────────────────────────────────────
    # Por defecto: cada domingo a las 3:00 AM (hora de Madrid)
    # Valores para SCHEDULER_DIA: mon, tue, wed, thu, fri, sat, sun
    SCHEDULER_ACTIVO = os.environ.get("SCHEDULER_ACTIVO", "true").lower() == "true"
    SCHEDULER_DIA    = os.environ.get("SCHEDULER_DIA",  "sun")
    SCHEDULER_HORA   = int(os.environ.get("SCHEDULER_HORA", 3))

    # ── Dateparser ───────────────────────────────────────────────────────────
    # Configuración para que dateparser interprete las fechas en español
    DATEPARSER_SETTINGS = {
        "PREFER_DAY_OF_MONTH": "first",
        "RETURN_AS_TIMEZONE_AWARE": False,
        "PREFER_LOCALE_DATE_ORDER": True,
    }
