"""
database/conexion.py — Gestión de la conexión a SQLite.

Patrón usado: Context Manager.
Garantiza que la conexión siempre se cierre aunque ocurra un error,
y que los cambios se hagan en una transacción atómica (todo o nada).
"""

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

from app.config import Config

logger = logging.getLogger(__name__)


def inicializar_base_de_datos():
    """
    Crea las tablas si no existen todavía.
    Se llama una sola vez al arrancar la aplicación.
    """
    esquema_path = Path(__file__).parent / "esquema.sql"
    esquema_sql  = esquema_path.read_text(encoding="utf-8")

    with obtener_conexion() as conn:
        # executescript ejecuta múltiples sentencias SQL separadas por ;
        conn.executescript(esquema_sql)

    logger.info("Base de datos inicializada en: %s", Config.DB_PATH)


@contextmanager
def obtener_conexion():
    """
    Context manager que abre y cierra la conexión de forma segura.

    Uso:
        with obtener_conexion() as conn:
            conn.execute("SELECT ...")

    Si ocurre cualquier excepción dentro del bloque 'with':
      → Se hace rollback (se deshacen los cambios)
      → Se cierra la conexión
      → La excepción se propaga hacia arriba para que la capa superior la gestione
    """
    conn = None
    try:
        conn = sqlite3.connect(
            Config.DB_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES,   # Convierte tipos automáticamente
            timeout=10,                              # Espera hasta 10s si la BD está bloqueada
        )
        # Row factory: permite acceder a las columnas por nombre (fila["nombre"])
        # en lugar de por índice (fila[0])
        conn.row_factory = sqlite3.Row

        # Activar claves foráneas (SQLite las ignora por defecto)
        conn.execute("PRAGMA foreign_keys = ON")

        yield conn
        conn.commit()

    except sqlite3.Error as e:
        logger.error("Error de base de datos: %s", e, exc_info=True)
        if conn:
            conn.rollback()
        raise   # Re-lanzamos para que la capa de servicio lo gestione

    finally:
        if conn:
            conn.close()
