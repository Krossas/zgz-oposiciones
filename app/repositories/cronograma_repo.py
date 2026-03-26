"""
repositories/cronograma_repo.py — Repositorio del cronograma de procesos.

Gestiona la persistencia de los datos del PDF de cronograma publicado
por el Ayuntamiento con el calendario previsto de todos los procesos.
"""

import json
import logging
from datetime import datetime

from app.database.conexion import obtener_conexion

logger = logging.getLogger(__name__)


class CronogramaRepository:
    """Gestiona las operaciones de base de datos del cronograma."""

    def reemplazar_cronograma(self, entradas: list[dict]) -> None:
        """
        Borra el cronograma anterior y lo reemplaza con los nuevos datos.
        El cronograma es un documento que se publica completo, no incremental,
        así que el enfoque correcto es reemplazarlo entero cada vez.
        """
        with obtener_conexion() as conn:
            conn.execute("DELETE FROM cronograma")
            conn.executemany(
                """INSERT INTO cronograma (proceso, fase, fechas, texto_completo, actualizado_en)
                   VALUES (?, ?, ?, ?, ?)""",
                [(
                    e.get("proceso"),
                    e.get("fase"),
                    json.dumps(e.get("fechas", []), ensure_ascii=False),
                    e.get("texto_completo"),
                    datetime.now().isoformat(),
                ) for e in entradas]
            )
        logger.info("Cronograma actualizado: %d entradas", len(entradas))

    def obtener_todo(self) -> list[dict]:
        """Devuelve todas las entradas del cronograma."""
        with obtener_conexion() as conn:
            filas = conn.execute(
                "SELECT * FROM cronograma ORDER BY proceso ASC"
            ).fetchall()

        resultado = []
        for f in filas:
            entrada           = dict(f)
            entrada["fechas"] = json.loads(entrada.get("fechas") or "[]")
            resultado.append(entrada)
        return resultado

    def buscar(self, texto: str) -> list[dict]:
        """Busca entradas del cronograma que coincidan con un texto."""
        with obtener_conexion() as conn:
            filas = conn.execute(
                "SELECT * FROM cronograma WHERE proceso LIKE ? ORDER BY proceso ASC",
                (f"%{texto}%",)
            ).fetchall()

        resultado = []
        for f in filas:
            entrada           = dict(f)
            entrada["fechas"] = json.loads(entrada.get("fechas") or "[]")
            resultado.append(entrada)
        return resultado

    def ultima_actualizacion(self) -> str | None:
        """Devuelve la fecha de la última actualización del cronograma."""
        with obtener_conexion() as conn:
            fila = conn.execute(
                "SELECT MAX(actualizado_en) FROM cronograma"
            ).fetchone()
        return fila[0] if fila else None
