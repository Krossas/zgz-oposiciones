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
        _migrar_esquema(conn)
        _limpiar_duplicados_oferta_anual(conn)
        _normalizar_urls_oferta(conn)

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


def _migrar_esquema(conn):
    """Aplica cambios incrementales a la base de datos existente."""
    columnas = [fila[1] for fila in conn.execute("PRAGMA table_info(oferta)").fetchall()]
    if "presentacion_instancias" not in columnas:
        conn.execute("ALTER TABLE oferta ADD COLUMN presentacion_instancias TEXT")
    if "instancia_inicio" not in columnas:
        conn.execute("ALTER TABLE oferta ADD COLUMN instancia_inicio TEXT")
    if "instancia_fin" not in columnas:
        conn.execute("ALTER TABLE oferta ADD COLUMN instancia_fin TEXT")


def _limpiar_duplicados_oferta_anual(conn):
    """Elimina duplicados antiguos de oferta_anual y normaliza oferta_id."""
    conn.execute("""
        DELETE FROM oferta_anual
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM oferta_anual
            GROUP BY anio, nombre, oferta_id
        )
    """)
    conn.execute("UPDATE oferta_anual SET oferta_id = '' WHERE oferta_id IS NULL")
    
    # Limpiar duplicados en 'oferta' basados en 'oferta_id' (mantener la versión más reciente)
    dup_ofertas = [r[0] for r in conn.execute("SELECT oferta_id FROM oferta WHERE oferta_id IS NOT NULL AND oferta_id != '' GROUP BY oferta_id HAVING COUNT(*) > 1").fetchall()]
    for oferta_id in dup_ofertas:
        fila = conn.execute("SELECT id FROM oferta WHERE oferta_id = ? ORDER BY datetime(actualizado_en) DESC LIMIT 1", (oferta_id,)).fetchone()
        if not fila:
            continue
        keep_id = fila[0]
        otros = [r[0] for r in conn.execute("SELECT id FROM oferta WHERE oferta_id = ? AND id != ?", (oferta_id, keep_id)).fetchall()]
        if otros:
            placeholders = ",".join(["?" for _ in otros])
            conn.execute(f"DELETE FROM oferta WHERE id IN ({placeholders})", otros)
    
    # NOTA: no se limpian duplicados por 'expediente' aquí porque la clave
    # autorizada para identificar fichas es 'oferta_id' (id de la URL).
    # Si en el pasado se generaron entradas duplicadas por expediente,
    # quedaron fuera de la limpieza automática para evitar borrar convocatorias
    # legítimas que comparten expediente.


def _normalizar_urls_oferta(conn):
    """Normaliza URLs malformadas en bases_url que falta /oferta/."""
    import re
    from urllib.parse import urljoin
    from app.config import Config
    
    # Buscar URLs que comienzan con https://www.zaragoza.es pero NO tienen /oferta/
    registros = conn.execute(
        "SELECT id, bases_url FROM oferta WHERE bases_url IS NOT NULL AND bases_url LIKE 'https://www.zaragoza.es%' AND bases_url NOT LIKE '%/oferta/%'"
    ).fetchall()
    
    for record in registros:
        record_id, bases_url = record[0], record[1]
        # Reparar la URL: insertar /oferta/ después del dominio
        fixed_url = bases_url.replace("https://www.zaragoza.es", "https://www.zaragoza.es/oferta", 1)
        if fixed_url != bases_url:
            conn.execute("UPDATE oferta SET bases_url = ? WHERE id = ?", (fixed_url, record_id))
            logger.debug("Normalizada bases_url en oferta %d: %s → %s", record_id, bases_url, fixed_url)
    
    # Lo mismo para url (enlaces a fichas de ofertas)
    registros_url = conn.execute(
        "SELECT id, url FROM oferta WHERE url IS NOT NULL AND url LIKE 'https://www.zaragoza.es%' AND url NOT LIKE '%/oferta/%'"
    ).fetchall()
    
    for record in registros_url:
        record_id, url = record[0], record[1]
        fixed_url = url.replace("https://www.zaragoza.es", "https://www.zaragoza.es/oferta", 1)
        if fixed_url != url:
            conn.execute("UPDATE oferta SET url = ? WHERE id = ?", (fixed_url, record_id))
            logger.debug("Normalizada url en oferta %d: %s → %s", record_id, url, fixed_url)
