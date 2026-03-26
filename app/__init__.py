"""
app/__init__.py — Factoría de la aplicación Flask.

Patrón usado: Application Factory.
En lugar de crear la app como variable global, la creamos dentro de una función.
Esto facilita los tests y permite múltiples configuraciones (dev, producción, test).
"""

import logging
import logging.handlers
from pathlib import Path

from flask import Flask, render_template

from app.config   import Config
from app.database.conexion import inicializar_base_de_datos


def crear_app() -> Flask:
    """
    Crea y configura la aplicación Flask.
    Llamada una sola vez desde run.py al arrancar.
    """
    app = Flask(__name__, template_folder="templates")

    # ── 1. Configurar logging ─────────────────────────────────────────────────
    _configurar_logging()

    logger = logging.getLogger(__name__)
    logger.info("Iniciando aplicación Oposiciones Zaragoza")

    # ── 2. Crear directorios necesarios ───────────────────────────────────────
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    Config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── 3. Inicializar base de datos ──────────────────────────────────────────
    inicializar_base_de_datos()

    # ── 4. Registrar blueprints (grupos de rutas) ─────────────────────────────
    from app.api.rutas import api_bp
    app.register_blueprint(api_bp)

    # ── 5. Arrancar el scheduler de tareas automáticas ───────────────────────
    if Config.SCHEDULER_ACTIVO:
        from app.services.scheduler import iniciar_scheduler, parar_scheduler
        import atexit
        iniciar_scheduler()
        # Parar el scheduler limpiamente al cerrar la aplicación
        atexit.register(parar_scheduler)
    else:
        logger.info("Scheduler desactivado (SCHEDULER_ACTIVO=false)")

    # ── 6. Ruta principal — sirve el frontend ─────────────────────────────────
    @app.route("/")
    def index():
        return render_template("index.html")

    # ── 6. Manejadores de errores HTTP ────────────────────────────────────────
    @app.errorhandler(404)
    def no_encontrado(e):
        logger.warning("404: %s", e)
        return {"ok": False, "error": "Recurso no encontrado"}, 404

    @app.errorhandler(500)
    def error_interno(e):
        logger.error("500: %s", e, exc_info=True)
        return {"ok": False, "error": "Error interno del servidor"}, 500

    logger.info("Aplicación lista en http://localhost:%d", Config.PORT)
    return app


def _configurar_logging():
    """
    Configura el sistema de logging:
    - Consola: nivel INFO, formato compacto
    - Fichero: nivel DEBUG, formato detallado, rotación automática
    """
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    formato_consola = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    formato_fichero = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler de consola — solo INFO y superiores para no saturar
    handler_consola = logging.StreamHandler()
    handler_consola.setLevel(logging.INFO)
    handler_consola.setFormatter(formato_consola)

    # Handler de fichero con rotación automática
    # RotatingFileHandler: cuando el fichero llega a LOG_MAX_BYTES,
    # lo renombra a app.log.1 y crea uno nuevo. Conserva LOG_BACKUPS copias.
    handler_fichero = logging.handlers.RotatingFileHandler(
        filename=Config.LOG_FILE,
        maxBytes=Config.LOG_MAX_BYTES,
        backupCount=Config.LOG_BACKUPS,
        encoding="utf-8"
    )
    handler_fichero.setLevel(logging.DEBUG)
    handler_fichero.setFormatter(formato_fichero)

    # Configurar el logger raíz — todos los módulos heredan esta configuración
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler_consola)
    root_logger.addHandler(handler_fichero)

    # Silenciar loggers muy verbosos de librerías externas
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
