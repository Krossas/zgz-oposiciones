"""
repositories/oferta_repo.py — Repositorio de ofertas.

Patrón usado: Repository.
Toda la lógica de acceso a la base de datos (SQL) vive aquí.
El resto de la aplicación nunca escribe SQL directamente;
usa este repositorio. Así, si un día cambias de SQLite a PostgreSQL,
solo tienes que modificar este fichero.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.database.conexion import obtener_conexion
from app.utils.cache import cached, cache_larga, cache_media

logger = logging.getLogger(__name__)


class OfertaRepository:
    """
    Gestiona todas las operaciones de base de datos relacionadas con ofertas,
    anuncios y cuadros de ofertas anuales.
    """

    # ── Ofertas ──────────────────────────────────────────────────────────────

    def guardar_oferta(self, datos: dict) -> None:
        """
        Inserta o actualiza una oferta.
        Si ya existe una oferta con el mismo oferta_id, actualiza sus datos.
        (Patrón UPSERT: UPDATE + INSERT en una sola operación)
        """
        sql = """
            INSERT INTO oferta (
                oferta_id, nombre, grupo, anio, turno, plantilla, escala,
                expediente, plazas, tipo_examen, titulacion, observaciones,
                convocatoria_bop, convocatoria_boe, fecha_instancia, bases_url,
                url, estado, es_activa, ultimo_scrape, actualizado_en
            ) VALUES (
                :oferta_id, :nombre, :grupo, :anio, :turno, :plantilla, :escala,
                :expediente, :plazas, :tipo_examen, :titulacion, :observaciones,
                :convocatoria_bop, :convocatoria_boe, :fecha_instancia, :bases_url,
                :url, :estado, :es_activa, :ultimo_scrape, :actualizado_en
            )
            ON CONFLICT(oferta_id) DO UPDATE SET
                nombre           = excluded.nombre,
                grupo            = excluded.grupo,
                anio             = excluded.anio,
                turno            = excluded.turno,
                plantilla        = excluded.plantilla,
                escala           = excluded.escala,
                expediente       = excluded.expediente,
                plazas           = excluded.plazas,
                tipo_examen      = excluded.tipo_examen,
                titulacion       = excluded.titulacion,
                observaciones    = excluded.observaciones,
                convocatoria_bop = excluded.convocatoria_bop,
                convocatoria_boe = excluded.convocatoria_boe,
                fecha_instancia  = excluded.fecha_instancia,
                bases_url        = excluded.bases_url,
                url              = excluded.url,
                estado           = excluded.estado,
                es_activa        = excluded.es_activa,
                ultimo_scrape    = excluded.ultimo_scrape,
                actualizado_en   = excluded.actualizado_en
        """
        # SQLite con parametros nombrados exige que todos los campos esten en el dict.
        for campo in ["turno", "plantilla", "escala", "expediente", "plazas",
                      "tipo_examen", "titulacion", "observaciones", "convocatoria_bop",
                      "convocatoria_boe", "fecha_instancia", "bases_url", "url",
                      "nombre", "grupo", "anio"]:
            datos.setdefault(campo, None)
        datos.setdefault("estado",         "pendiente")
        datos.setdefault("es_activa",      0)
        datos.setdefault("ultimo_scrape",  datetime.now().isoformat())
        datos.setdefault("actualizado_en", datetime.now().isoformat())
        with obtener_conexion() as conn:
            conn.execute(sql, datos)
        logger.debug("Oferta guardada: %s — %s", datos.get("oferta_id"), datos.get("nombre"))

    def marcar_todas_inactivas(self) -> None:
        """
        Marca todas las ofertas como inactivas antes de un scraping.
        Después del scraping, las que siguen en zaragoza.es se reactivarán.
        Las que no aparezcan quedan inactivas (proceso cerrado/terminado).
        """
        with obtener_conexion() as conn:
            conn.execute("UPDATE oferta SET es_activa = 0")
        logger.info("Todas las ofertas marcadas como inactivas")

    def obtener_activas(self, grupo: str = None, estado: str = None,
                        busqueda: str = None) -> list[dict]:
        """
        Devuelve los procesos actualmente abiertos con filtros opcionales.
        Usa FTS5 si se proporciona búsqueda de texto.
        """
        condiciones = ["es_activa = 1"]
        params      = {}

        if grupo:
            condiciones.append("grupo = :grupo")
            params["grupo"] = grupo
        if estado:
            condiciones.append("estado = :estado")
            params["estado"] = estado

        with obtener_conexion() as conn:
            if busqueda:
                terminos  = [f'"{t}"*' for t in busqueda.replace('"', '').split() if t]
                query_fts = " ".join(terminos) if terminos else f'"{busqueda}"*'
                where_extra = "AND " + " AND ".join(condiciones[1:]) if len(condiciones) > 1 else ""
                params["query"] = query_fts
                sql = f"""
                    SELECT o.* FROM oferta o
                    INNER JOIN oferta_fts ON oferta_fts.oferta_id = o.oferta_id
                    WHERE oferta_fts MATCH :query AND o.es_activa = 1 {where_extra}
                    ORDER BY rank, o.nombre ASC
                """
            else:
                where = "WHERE " + " AND ".join(condiciones)
                sql   = f"SELECT * FROM oferta {where} ORDER BY nombre ASC"

            filas = conn.execute(sql, params).fetchall()
        return [dict(f) for f in filas]

    def obtener_todas(self, anio: int = None, grupo: str = None,
                      estado: str = None, busqueda: str = None,
                      pagina: int = 1, por_pagina: int = 100) -> dict:
        """
        Devuelve ofertas con filtros opcionales y paginación.

        Cuando hay búsqueda de texto usa FTS5 (Full Text Search de SQLite),
        que soporta prefijos (admin*), es insensible a mayúsculas/minúsculas
        y mucho más rápido que LIKE en tablas grandes.

        Devuelve un dict con:
            - items:      lista de ofertas de la página actual
            - total:      total de resultados (para calcular páginas en el frontend)
            - pagina:     página actual
            - por_pagina: registros por página
            - paginas:    total de páginas
        """
        condiciones = []
        params      = {}

        if anio:
            condiciones.append("anio = :anio")
            params["anio"] = anio
        if grupo:
            condiciones.append("grupo = :grupo")
            params["grupo"] = grupo
        if estado:
            condiciones.append("estado = :estado")
            params["estado"] = estado

        with obtener_conexion() as conn:
            if busqueda:
                # FTS5: normalizar la query — añadir * para búsqueda por prefijo
                # Escapar comillas para evitar errores de sintaxis FTS5
                query_fts = busqueda.replace('"', '""').strip()
                # Si la búsqueda tiene varias palabras, buscar cada una por prefijo
                terminos  = [f'"{t}"*' for t in query_fts.split() if t]
                query_fts = " ".join(terminos) if terminos else f'"{query_fts}"*'

                # JOIN con FTS5 para obtener solo los IDs que coinciden
                where_extra = ("AND " + " AND ".join(condiciones)) if condiciones else ""
                sql_ids = f"""
                    SELECT o.id FROM oferta o
                    INNER JOIN oferta_fts ON oferta_fts.oferta_id = o.oferta_id
                    WHERE oferta_fts MATCH :query {where_extra}
                    ORDER BY rank, o.anio DESC
                """
                params["query"] = query_fts
                ids = [r[0] for r in conn.execute(sql_ids, params).fetchall()]

                total = len(ids)
                # Paginar los IDs
                inicio = (pagina - 1) * por_pagina
                ids_pagina = ids[inicio: inicio + por_pagina]

                if not ids_pagina:
                    filas = []
                else:
                    placeholders = ",".join("?" * len(ids_pagina))
                    filas = conn.execute(
                        f"SELECT * FROM oferta WHERE id IN ({placeholders}) ORDER BY anio DESC, nombre ASC",
                        ids_pagina
                    ).fetchall()
            else:
                # Sin búsqueda de texto: SQL normal con paginación
                where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
                total = conn.execute(f"SELECT COUNT(*) FROM oferta {where}", params).fetchone()[0]

                params["limite"] = por_pagina
                params["offset"] = (pagina - 1) * por_pagina
                filas = conn.execute(
                    f"SELECT * FROM oferta {where} ORDER BY anio DESC, nombre ASC LIMIT :limite OFFSET :offset",
                    params
                ).fetchall()

        import math
        return {
            "items":      [dict(f) for f in filas],
            "total":      total,
            "pagina":     pagina,
            "por_pagina": por_pagina,
            "paginas":    math.ceil(total / por_pagina) if total else 1,
        }

    def obtener_por_id(self, oferta_id: str) -> Optional[dict]:
        """Devuelve una oferta concreta con todos sus anuncios."""
        with obtener_conexion() as conn:
            oferta = conn.execute(
                "SELECT * FROM oferta WHERE oferta_id = ?", (oferta_id,)
            ).fetchone()

            if not oferta:
                return None

            anuncios = conn.execute(
                "SELECT * FROM anuncio WHERE oferta_id = ? ORDER BY fecha DESC",
                (oferta_id,)
            ).fetchall()

        resultado         = dict(oferta)
        resultado["anuncios"] = [dict(a) for a in anuncios]
        return resultado

    def existe(self, oferta_id: str) -> bool:
        """Comprueba si ya tenemos datos de una oferta."""
        with obtener_conexion() as conn:
            fila = conn.execute(
                "SELECT 1 FROM oferta WHERE oferta_id = ?", (oferta_id,)
            ).fetchone()
        return fila is not None

    # ── Anuncios ─────────────────────────────────────────────────────────────

    def reemplazar_anuncios(self, oferta_id: str, anuncios: list[dict]) -> None:
        """
        Borra los anuncios anteriores de una oferta y los reemplaza.
        Más sencillo que intentar hacer un UPSERT de cada anuncio individual.
        """
        with obtener_conexion() as conn:
            conn.execute("DELETE FROM anuncio WHERE oferta_id = ?", (oferta_id,))
            conn.executemany(
                "INSERT INTO anuncio (oferta_id, fecha, texto, url) VALUES (?, ?, ?, ?)",
                [(oferta_id, a.get("fecha"), a.get("texto"), a.get("url")) for a in anuncios]
            )

    # ── Cuadros anuales ───────────────────────────────────────────────────────

    def guardar_oferta_anual(self, datos: dict) -> None:
        """Inserta o ignora una entrada del cuadro de ofertas anual."""
        sql = """
            INSERT OR IGNORE INTO oferta_anual
                (anio, nombre, oferta_id, plazas, grupo, procedimiento, titulacion, observaciones, url)
            VALUES
                (:anio, :nombre, :oferta_id, :plazas, :grupo, :procedimiento, :titulacion, :observaciones, :url)
        """
        with obtener_conexion() as conn:
            conn.execute(sql, datos)

    def obtener_anuales(self, anio: int = None) -> list[dict]:
        """Devuelve el cuadro de ofertas, opcionalmente filtrado por año."""
        if anio:
            sql    = "SELECT * FROM oferta_anual WHERE anio = ? ORDER BY nombre ASC"
            params = (anio,)
        else:
            sql    = "SELECT * FROM oferta_anual ORDER BY anio DESC, nombre ASC"
            params = ()

        with obtener_conexion() as conn:
            filas = conn.execute(sql, params).fetchall()
        return [dict(f) for f in filas]

    @cached(cache_larga, key_fn=lambda self: 'anios')
    def obtener_anios_disponibles(self) -> list[int]:
        """Lista de años de los que tenemos cuadro de ofertas."""
        with obtener_conexion() as conn:
            filas = conn.execute(
                "SELECT DISTINCT anio FROM oferta_anual ORDER BY anio DESC"
            ).fetchall()
        return [f["anio"] for f in filas]

    # ── Estadísticas ──────────────────────────────────────────────────────────

    @cached(cache_media, key_fn=lambda self: 'estadisticas')
    def obtener_estadisticas(self) -> dict:
        """
        Agrega estadísticas generales de la base de datos.
        Una sola consulta por métrica para eficiencia.
        """
        with obtener_conexion() as conn:
            total_ofertas  = conn.execute("SELECT COUNT(*) FROM oferta").fetchone()[0]
            activas        = conn.execute("SELECT COUNT(*) FROM oferta WHERE es_activa = 1").fetchone()[0]
            total_anuales  = conn.execute("SELECT COUNT(*) FROM oferta_anual").fetchone()[0]

            por_estado     = conn.execute(
                "SELECT estado, COUNT(*) as n FROM oferta WHERE es_activa = 1 GROUP BY estado"
            ).fetchall()

            por_grupo      = conn.execute(
                "SELECT grupo, COUNT(*) as n FROM oferta_anual WHERE grupo IS NOT NULL GROUP BY grupo ORDER BY n DESC"
            ).fetchall()

            por_anio       = conn.execute(
                "SELECT anio, COUNT(*) as n FROM oferta_anual GROUP BY anio ORDER BY anio DESC"
            ).fetchall()

        return {
            "total_ofertas": total_ofertas,
            "activas":       activas,
            "total_anuales": total_anuales,
            "por_estado":    {f["estado"]: f["n"] for f in por_estado},
            "por_grupo":     {f["grupo"]: f["n"]  for f in por_grupo},
            "por_anio":      {f["anio"]:  f["n"]  for f in por_anio},
        }

    @cached(cache_larga, key_fn=lambda self: 'frecuencia')
    def obtener_frecuencia(self) -> list[dict]:
        """
        Análisis de frecuencia: cuántas veces aparece cada puesto a lo largo
        de los años, en qué años y cuántas plazas en total.

        Agrupa por nombre normalizado (sin distinguir mayúsculas/minúsculas
        y sin los sufijos de tipo de turno entre paréntesis).
        """
        sql = """
            SELECT
                nombre,
                COUNT(DISTINCT anio) AS num_convocatorias,
                GROUP_CONCAT(DISTINCT anio ORDER BY anio ASC) AS anios,
                GROUP_CONCAT(DISTINCT grupo) AS grupos,
                SUM(CAST(REPLACE(plazas, ',', '') AS INTEGER)) AS total_plazas
            FROM oferta_anual
            GROUP BY LOWER(TRIM(nombre))
            ORDER BY num_convocatorias DESC, nombre ASC
        """
        with obtener_conexion() as conn:
            filas = conn.execute(sql).fetchall()

        resultado = []
        for f in filas:
            resultado.append({
                "nombre":            f["nombre"],
                "num_convocatorias": f["num_convocatorias"],
                "anios":             f["anios"].split(",") if f["anios"] else [],
                "grupos":            list(set(f["grupos"].split(","))) if f["grupos"] else [],
                "total_plazas":      f["total_plazas"] or 0,
            })
        return resultado
