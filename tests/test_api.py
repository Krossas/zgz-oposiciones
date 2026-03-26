"""
tests/test_api.py — Tests de los endpoints REST de la API.

Usan el cliente de test de Flask para hacer peticiones HTTP reales
(sin levantar un servidor de verdad) y verificar respuestas.

Se comprueba tanto el código HTTP como la estructura del JSON devuelto.
"""

import json
import pytest


class TestEndpointEstado:
    """Tests del endpoint /api/estado."""

    def test_estado_devuelve_200(self, client):
        r = client.get("/api/estado")
        assert r.status_code == 200

    def test_estado_devuelve_estructura_correcta(self, client):
        r    = client.get("/api/estado")
        data = r.get_json()
        assert data["ok"] is True
        assert "datos" in data
        assert "en_curso" in data["datos"]
        assert "version"  in data["datos"]


class TestEndpointActivas:
    """Tests del endpoint /api/activas."""

    def test_activas_vacio_devuelve_lista_vacia(self, client):
        r    = client.get("/api/activas")
        data = r.get_json()
        assert data["ok"] is True
        assert data["datos"] == []

    def test_activas_con_datos(self, client, repo_oferta, oferta_ejemplo):
        repo_oferta.guardar_oferta(oferta_ejemplo)
        r    = client.get("/api/activas")
        data = r.get_json()
        assert data["ok"]         is True
        assert len(data["datos"]) == 1
        assert data["datos"][0]["nombre"] == "Administrativo/a (Test)"

    def test_activas_filtro_grupo_valido(self, client, repo_oferta, oferta_ejemplo):
        repo_oferta.guardar_oferta(oferta_ejemplo)
        r    = client.get("/api/activas?grupo=C1")
        data = r.get_json()
        assert data["ok"] is True
        assert len(data["datos"]) == 1

    def test_activas_filtro_grupo_invalido_devuelve_400(self, client):
        r = client.get("/api/activas?grupo=Z9")
        assert r.status_code == 400
        assert r.get_json()["ok"] is False

    def test_activas_filtro_grupo_sin_resultados(self, client, repo_oferta, oferta_ejemplo):
        repo_oferta.guardar_oferta(oferta_ejemplo)   # grupo C1
        r    = client.get("/api/activas?grupo=A1")
        data = r.get_json()
        assert data["ok"]         is True
        assert len(data["datos"]) == 0


class TestEndpointOfertas:
    """Tests del endpoint /api/ofertas (paginado)."""

    def test_ofertas_devuelve_estructura_paginada(self, client):
        r    = client.get("/api/ofertas")
        data = r.get_json()
        assert data["ok"] is True
        assert "items"      in data["datos"]
        assert "total"      in data["datos"]
        assert "pagina"     in data["datos"]
        assert "por_pagina" in data["datos"]
        assert "paginas"    in data["datos"]

    def test_ofertas_paginacion(self, client, repo_oferta, oferta_ejemplo):
        # Insertar 5 ofertas
        for i in range(5):
            repo_oferta.guardar_oferta({**oferta_ejemplo, "oferta_id": str(1000+i), "nombre": f"Oferta {i}"})

        r    = client.get("/api/ofertas?pagina=1&por_pagina=2")
        data = r.get_json()["datos"]
        assert data["total"]      == 5
        assert data["paginas"]    == 3
        assert len(data["items"]) == 2

    def test_ofertas_anio_invalido_devuelve_400(self, client):
        r = client.get("/api/ofertas?anio=abc")
        assert r.status_code == 400

    def test_ofertas_por_pagina_demasiado_grande_devuelve_400(self, client):
        r = client.get("/api/ofertas?por_pagina=999")
        assert r.status_code == 400

    def test_busqueda_muy_corta_devuelve_400(self, client):
        r = client.get("/api/ofertas?busqueda=a")
        assert r.status_code == 400


class TestEndpointDetalle:
    """Tests del endpoint /api/ofertas/<id>."""

    def test_detalle_existente(self, client, repo_oferta, oferta_ejemplo):
        repo_oferta.guardar_oferta(oferta_ejemplo)
        r    = client.get("/api/ofertas/9999")
        data = r.get_json()
        assert data["ok"] is True
        assert data["datos"]["oferta_id"] == "9999"
        assert "anuncios" in data["datos"]

    def test_detalle_no_existente_devuelve_404(self, client):
        r = client.get("/api/ofertas/1234")
        assert r.status_code == 404
        assert r.get_json()["ok"] is False

    def test_detalle_id_invalido_devuelve_400(self, client):
        r = client.get("/api/ofertas/abc")
        assert r.status_code == 400


class TestEndpointAnnuales:
    """Tests del endpoint /api/anuales."""

    def test_anuales_vacio(self, client):
        r = client.get("/api/anuales")
        assert r.status_code == 200
        assert r.get_json()["datos"] == []

    def test_anuales_filtrado_por_anio(self, client, repo_oferta):
        repo_oferta.guardar_oferta_anual({
            "anio": 2025, "nombre": "Test 2025", "oferta_id": None,
            "plazas": "5", "grupo": "C1", "procedimiento": None,
            "titulacion": None, "observaciones": None, "url": None,
        })
        repo_oferta.guardar_oferta_anual({
            "anio": 2024, "nombre": "Test 2024", "oferta_id": None,
            "plazas": "3", "grupo": "A1", "procedimiento": None,
            "titulacion": None, "observaciones": None, "url": None,
        })

        r    = client.get("/api/anuales?anio=2025")
        data = r.get_json()
        assert len(data["datos"]) == 1
        assert data["datos"][0]["nombre"] == "Test 2025"

    def test_anuales_anio_invalido_devuelve_400(self, client):
        r = client.get("/api/anuales?anio=noesunnumero")
        assert r.status_code == 400


class TestEndpointFrecuencia:
    """Tests del endpoint /api/frecuencia."""

    def test_frecuencia_vacia(self, client):
        r = client.get("/api/frecuencia")
        assert r.status_code  == 200
        assert r.get_json()["datos"] == []

    def test_frecuencia_con_datos(self, client, repo_oferta):
        for anio in [2023, 2024, 2025]:
            repo_oferta.guardar_oferta_anual({
                "anio": anio, "nombre": "Administrativo/a", "oferta_id": None,
                "plazas": "10", "grupo": "C1", "procedimiento": None,
                "titulacion": None, "observaciones": None, "url": None,
            })

        r    = client.get("/api/frecuencia")
        data = r.get_json()["datos"]
        assert len(data) == 1
        assert data[0]["num_convocatorias"] == 3


class TestEndpointCronograma:
    """Tests del endpoint /api/cronograma."""

    def test_cronograma_vacio(self, client):
        r    = client.get("/api/cronograma")
        data = r.get_json()
        assert data["ok"] is True
        assert data["datos"]["entradas"] == []

    def test_cronograma_con_datos(self, client):
        from app.repositories.cronograma_repo import CronogramaRepository
        repo = CronogramaRepository()
        repo.reemplazar_cronograma([
            {"proceso": "Administrativo", "fase": "Examen", "fechas": ["15/06/2026"], "texto_completo": "..."},
        ])

        r    = client.get("/api/cronograma")
        data = r.get_json()["datos"]
        assert len(data["entradas"]) == 1
        assert data["entradas"][0]["proceso"] == "Administrativo"

    def test_cronograma_busqueda_corta_devuelve_400(self, client):
        r = client.get("/api/cronograma?busqueda=a")
        assert r.status_code == 400


class TestEndpointScheduler:
    """Tests del endpoint /api/scheduler."""

    def test_scheduler_devuelve_estado(self, client):
        r    = client.get("/api/scheduler")
        data = r.get_json()
        assert data["ok"] is True
        # En tests el scheduler está desactivado (Config.SCHEDULER_ACTIVO = False)
        assert data["datos"]["activo"] is False


class TestRespuestasDeError:
    """Tests de que los errores siguen la estructura estándar."""

    def test_404_sigue_estructura(self, client):
        r    = client.get("/api/ofertas/9999")
        data = r.get_json()
        assert r.status_code == 404
        assert data["ok"]    is False
        assert "error"       in data

    def test_400_sigue_estructura(self, client):
        r    = client.get("/api/ofertas?anio=abc")
        data = r.get_json()
        assert r.status_code == 400
        assert data["ok"]    is False
        assert "error"       in data
        # El mensaje debe ser legible, no un traceback técnico
        assert "abc" in data["error"] or "entero" in data["error"]
