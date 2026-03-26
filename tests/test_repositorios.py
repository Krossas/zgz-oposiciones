"""
tests/test_repositorios.py — Tests de la capa de repositorios.

Comprueban que el acceso a base de datos funciona correctamente:
inserciones, consultas, upserts, filtros y búsquedas FTS5.

Usan la BD de test (fichero temporal) definida en conftest.py.
"""

import pytest


class TestOfertaRepository:
    """Tests del repositorio de ofertas."""

    def test_guardar_y_recuperar_oferta(self, repo_oferta, oferta_ejemplo):
        """Guardar una oferta y recuperarla por ID debe devolver los mismos datos."""
        repo_oferta.guardar_oferta(oferta_ejemplo)
        recuperada = repo_oferta.obtener_por_id("9999")

        assert recuperada is not None
        assert recuperada["nombre"]  == "Administrativo/a (Test)"
        assert recuperada["grupo"]   == "C1"
        assert recuperada["anio"]    == 2025
        assert recuperada["anuncios"] == []   # Sin anuncios todavía

    def test_upsert_actualiza_datos_existentes(self, repo_oferta, oferta_ejemplo):
        """Guardar una oferta que ya existe debe actualizar sus datos, no duplicarla."""
        repo_oferta.guardar_oferta(oferta_ejemplo)

        # Actualizar el nombre
        modificada = {**oferta_ejemplo, "nombre": "Administrativo/a (Modificado)"}
        repo_oferta.guardar_oferta(modificada)

        todas = repo_oferta.obtener_todas()
        assert todas["total"] == 1   # Solo un registro
        assert todas["items"][0]["nombre"] == "Administrativo/a (Modificado)"

    def test_obtener_activas_solo_devuelve_activas(self, repo_oferta, oferta_ejemplo):
        """obtener_activas no debe devolver ofertas inactivas."""
        repo_oferta.guardar_oferta(oferta_ejemplo)   # es_activa=1
        repo_oferta.guardar_oferta({
            **oferta_ejemplo,
            "oferta_id": "8888",
            "nombre":    "Arquitecto/a (Inactivo)",
            "es_activa": 0,
        })

        activas = repo_oferta.obtener_activas()
        assert len(activas) == 1
        assert activas[0]["oferta_id"] == "9999"

    def test_marcar_todas_inactivas(self, repo_oferta, oferta_ejemplo):
        """marcar_todas_inactivas debe poner es_activa=0 en todas las filas."""
        repo_oferta.guardar_oferta(oferta_ejemplo)
        repo_oferta.marcar_todas_inactivas()

        activas = repo_oferta.obtener_activas()
        assert len(activas) == 0

    def test_filtro_por_grupo(self, repo_oferta, oferta_ejemplo):
        """El filtro de grupo debe devolver solo las ofertas de ese grupo."""
        repo_oferta.guardar_oferta(oferta_ejemplo)   # grupo C1
        repo_oferta.guardar_oferta({
            **oferta_ejemplo,
            "oferta_id": "8888",
            "nombre":    "Arquitecto/a",
            "grupo":     "A1",
        })

        resultado = repo_oferta.obtener_todas(grupo="C1")
        assert resultado["total"] == 1
        assert resultado["items"][0]["grupo"] == "C1"

    def test_filtro_por_anio(self, repo_oferta, oferta_ejemplo):
        """El filtro de año debe devolver solo las ofertas de ese año."""
        repo_oferta.guardar_oferta(oferta_ejemplo)   # anio 2025
        repo_oferta.guardar_oferta({
            **oferta_ejemplo,
            "oferta_id": "8888",
            "nombre":    "Otra oferta",
            "anio":      2024,
        })

        resultado = repo_oferta.obtener_todas(anio=2025)
        assert resultado["total"] == 1
        assert resultado["items"][0]["anio"] == 2025

    def test_paginacion(self, repo_oferta, oferta_ejemplo):
        """La paginación debe dividir los resultados correctamente."""
        # Insertar 5 ofertas
        for i in range(5):
            repo_oferta.guardar_oferta({
                **oferta_ejemplo,
                "oferta_id": str(1000 + i),
                "nombre":    f"Oferta {i}",
            })

        pagina1 = repo_oferta.obtener_todas(pagina=1, por_pagina=2)
        pagina2 = repo_oferta.obtener_todas(pagina=2, por_pagina=2)
        pagina3 = repo_oferta.obtener_todas(pagina=3, por_pagina=2)

        assert pagina1["total"]   == 5
        assert pagina1["paginas"] == 3
        assert len(pagina1["items"]) == 2
        assert len(pagina2["items"]) == 2
        assert len(pagina3["items"]) == 1   # Última página con 1 elemento

    def test_existe_devuelve_true_si_hay_oferta(self, repo_oferta, oferta_ejemplo):
        repo_oferta.guardar_oferta(oferta_ejemplo)
        assert repo_oferta.existe("9999") is True

    def test_existe_devuelve_false_si_no_hay_oferta(self, repo_oferta):
        assert repo_oferta.existe("0000") is False

    def test_anuncios_se_guardan_y_recuperan(self, repo_oferta, oferta_ejemplo):
        """Los anuncios deben asociarse a su oferta y recuperarse con ella."""
        repo_oferta.guardar_oferta(oferta_ejemplo)
        anuncios = [
            {"fecha": "20/11/2025", "texto": "Bases de la convocatoria", "url": "http://ejemplo.es/bases"},
            {"fecha": "28/12/2025", "texto": "Presentación de instancias", "url": None},
        ]
        repo_oferta.reemplazar_anuncios("9999", anuncios)

        oferta = repo_oferta.obtener_por_id("9999")
        assert len(oferta["anuncios"]) == 2
        assert oferta["anuncios"][0]["texto"] == "Presentación de instancias"   # Orden DESC por fecha

    def test_reemplazar_anuncios_borra_los_anteriores(self, repo_oferta, oferta_ejemplo):
        """reemplazar_anuncios debe borrar los previos, no acumularlos."""
        repo_oferta.guardar_oferta(oferta_ejemplo)
        repo_oferta.reemplazar_anuncios("9999", [{"fecha": "01/01/2025", "texto": "Primero", "url": None}])
        repo_oferta.reemplazar_anuncios("9999", [{"fecha": "02/02/2025", "texto": "Segundo", "url": None}])

        oferta = repo_oferta.obtener_por_id("9999")
        assert len(oferta["anuncios"]) == 1
        assert oferta["anuncios"][0]["texto"] == "Segundo"

    def test_estadisticas_devuelve_contadores(self, repo_oferta, oferta_ejemplo):
        """obtener_estadisticas debe devolver contadores correctos."""
        repo_oferta.guardar_oferta(oferta_ejemplo)
        repo_oferta.guardar_oferta_anual({
            "anio": 2025, "nombre": "Administrativo/a", "oferta_id": "9999",
            "plazas": "10", "grupo": "C1", "procedimiento": None,
            "titulacion": None, "observaciones": None, "url": None,
        })

        stats = repo_oferta.obtener_estadisticas()
        assert stats["total_ofertas"]  == 1
        assert stats["activas"]        == 1
        assert stats["total_anuales"]  == 1
        assert "C1" in stats["por_grupo"]

    def test_frecuencia_agrupa_por_nombre(self, repo_oferta):
        """obtener_frecuencia debe agrupar por nombre y contar años."""
        for anio in [2023, 2024, 2025]:
            repo_oferta.guardar_oferta_anual({
                "anio": anio, "nombre": "Administrativo/a", "oferta_id": None,
                "plazas": "5", "grupo": "C1", "procedimiento": None,
                "titulacion": None, "observaciones": None, "url": None,
            })

        frecuencia = repo_oferta.obtener_frecuencia()
        assert len(frecuencia) == 1
        assert frecuencia[0]["nombre"]            == "Administrativo/a"
        assert frecuencia[0]["num_convocatorias"] == 3
        assert set(frecuencia[0]["anios"])        == {"2023", "2024", "2025"}


class TestLogRepository:
    """Tests del repositorio de logs de scraping."""

    def test_ciclo_completo_de_log(self, repo_log):
        """Crear, actualizar progreso, añadir error y finalizar un log."""
        log_id = repo_log.crear_log()
        assert log_id is not None

        repo_log.actualizar_progreso(log_id, "Fase 1 en curso...")
        repo_log.añadir_error(log_id, "Error en oferta 123")
        repo_log.finalizar_log(log_id, "completado", 50)

        ultimo = repo_log.obtener_ultimo()
        assert ultimo["estado"]            == "completado"
        assert ultimo["ofertas_guardadas"] == 50
        assert len(ultimo["errores"])      == 1
        assert "oferta 123" in ultimo["errores"][0]

    def test_historial_devuelve_logs_ordenados(self, repo_log):
        """El historial debe devolver los logs más recientes primero."""
        id1 = repo_log.crear_log()
        id2 = repo_log.crear_log()
        repo_log.finalizar_log(id1, "completado", 10)
        repo_log.finalizar_log(id2, "error", 0)

        historial = repo_log.obtener_historial()
        assert historial[0]["id"] == id2   # El más reciente primero

    def test_multiples_errores_en_mismo_log(self, repo_log):
        """Varios errores deben acumularse en el array JSON."""
        log_id = repo_log.crear_log()
        repo_log.añadir_error(log_id, "Error A")
        repo_log.añadir_error(log_id, "Error B")
        repo_log.añadir_error(log_id, "Error C")

        ultimo = repo_log.obtener_ultimo()
        assert len(ultimo["errores"]) == 3
