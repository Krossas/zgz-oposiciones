"""
repositories/log_repo.py — Repositorio de logs de scraping.

Persiste en base de datos el historial de cada operación de scraping:
cuándo se inició, cuánto tardó, cuántas ofertas se guardaron y qué errores
ocurrieron. Esto permite al usuario ver el historial y diagnosticar problemas.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.database.conexion import obtener_conexion

logger = logging.getLogger(__name__)


class LogRepository:
    """Gestiona el registro de operaciones de scraping en la base de datos."""

    def crear_log(self) -> int:
        """
        Crea un nuevo registro de scraping con estado 'en_curso'.
        Devuelve el ID del registro para actualizarlo después.
        """
        sql = """
            INSERT INTO log_scrape (iniciado_en, estado, progreso, errores)
            VALUES (?, 'en_curso', 'Iniciando...', '[]')
        """
        with obtener_conexion() as conn:
            cursor = conn.execute(sql, (datetime.now().isoformat(),))
            log_id = cursor.lastrowid

        logger.info("Log de scraping creado con ID: %d", log_id)
        return log_id

    def actualizar_progreso(self, log_id: int, progreso: str) -> None:
        """Actualiza el mensaje de progreso del scraping en curso."""
        with obtener_conexion() as conn:
            conn.execute(
                "UPDATE log_scrape SET progreso = ? WHERE id = ?",
                (progreso, log_id)
            )

    def añadir_error(self, log_id: int, mensaje_error: str) -> None:
        """
        Añade un error al array JSON de errores del log.
        Lee el array actual, añade el nuevo error y lo vuelve a escribir.
        """
        with obtener_conexion() as conn:
            fila = conn.execute(
                "SELECT errores FROM log_scrape WHERE id = ?", (log_id,)
            ).fetchone()

            if fila:
                errores = json.loads(fila["errores"] or "[]")
                errores.append(mensaje_error)
                conn.execute(
                    "UPDATE log_scrape SET errores = ? WHERE id = ?",
                    (json.dumps(errores, ensure_ascii=False), log_id)
                )

        logger.warning("Error registrado en log %d: %s", log_id, mensaje_error)

    def finalizar_log(self, log_id: int, estado: str, ofertas_guardadas: int) -> None:
        """
        Marca el scraping como completado o fallido.

        Args:
            log_id:            ID del log a finalizar
            estado:            'completado' o 'error'
            ofertas_guardadas: Cuántas ofertas se guardaron con éxito
        """
        sql = """
            UPDATE log_scrape
            SET finalizado_en     = ?,
                estado            = ?,
                ofertas_guardadas = ?,
                progreso          = ?
            WHERE id = ?
        """
        ahora    = datetime.now().isoformat()
        progreso = (
            f"Completado — {ofertas_guardadas} procesos guardados"
            if estado == "completado"
            else "Finalizado con errores"
        )

        with obtener_conexion() as conn:
            conn.execute(sql, (ahora, estado, ofertas_guardadas, progreso, log_id))

        logger.info("Log %d finalizado: %s (%d ofertas)", log_id, estado, ofertas_guardadas)

    def obtener_ultimo(self) -> Optional[dict]:
        """Devuelve el log del scraping más reciente."""
        sql = "SELECT * FROM log_scrape ORDER BY id DESC LIMIT 1"
        with obtener_conexion() as conn:
            fila = conn.execute(sql).fetchone()

        if not fila:
            return None

        resultado           = dict(fila)
        resultado["errores"] = json.loads(resultado.get("errores") or "[]")
        return resultado

    def obtener_historial(self, limite: int = 20) -> list[dict]:
        """Devuelve los últimos N scrapings realizados."""
        sql = "SELECT * FROM log_scrape ORDER BY id DESC LIMIT ?"
        with obtener_conexion() as conn:
            filas = conn.execute(sql, (limite,)).fetchall()

        resultado = []
        for f in filas:
            entrada           = dict(f)
            entrada["errores"] = json.loads(entrada.get("errores") or "[]")
            resultado.append(entrada)
        return resultado
