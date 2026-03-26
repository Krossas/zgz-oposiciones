"""
tests/conftest.py — Configuración compartida de los tests.

Define fixtures de pytest: objetos reutilizables que se inyectan
automáticamente en los tests que los necesitan.

El patrón clave aquí es usar una BD en memoria (:memory:) para los tests,
de modo que:
  - Los tests no modifican la BD real
  - Cada test parte de un estado limpio
  - Los tests corren rápido (sin I/O de disco)
"""

import os
import pytest

# Apuntar a una BD de test en memoria ANTES de importar nada de la app
os.environ["DB_PATH_TEST"] = ":memory:"


@pytest.fixture(scope="session")
def app():
    """
    Crea una instancia de la aplicación Flask configurada para tests.
    scope="session" significa que se crea una vez para toda la sesión de tests.
    """
    # Sobreescribir la ruta de BD para usar un fichero temporal de tests
    import tempfile, pathlib

    db_temp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_temp.close()

    # Parchear Config antes de crear la app
    from app.config import Config
    Config.DB_PATH        = pathlib.Path(db_temp.name)
    Config.SCHEDULER_ACTIVO = False   # No arrancar scheduler en tests
    Config.LOG_DIR        = pathlib.Path(tempfile.mkdtemp())
    Config.LOG_FILE       = Config.LOG_DIR / "test.log"

    from app import crear_app
    aplicacion = crear_app()
    aplicacion.config["TESTING"] = True

    yield aplicacion

    # Limpiar fichero temporal al acabar
    os.unlink(db_temp.name)


@pytest.fixture(scope="session")
def client(app):
    """Cliente HTTP de Flask para tests de la API."""
    return app.test_client()


@pytest.fixture(autouse=True)
def limpiar_bd():
    """
    Limpia las tablas relevantes antes de cada test individual.
    autouse=True significa que se ejecuta para todos los tests automáticamente.
    """
    # Limpiar también la caché para que los tests no se contaminen entre sí
    from app.utils.cache import invalidar_todo
    invalidar_todo()

    from app.database.conexion import obtener_conexion
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM anuncio")
        conn.execute("DELETE FROM oferta")
        conn.execute("DELETE FROM oferta_anual")
        conn.execute("DELETE FROM log_scrape")
        conn.execute("DELETE FROM cronograma")
        # Limpiar también el índice FTS5
        try:
            conn.execute("DELETE FROM oferta_fts")
            conn.execute("DELETE FROM oferta_anual_fts")
        except Exception:
            pass   # FTS5 puede no estar disponible en todos los entornos de test
    yield


@pytest.fixture
def oferta_ejemplo():
    """Datos de una oferta de ejemplo para reutilizar en tests."""
    return {
        "oferta_id": "9999",
        "nombre":    "Administrativo/a (Test)",
        "grupo":     "C1",
        "anio":      2025,
        "es_activa": 1,
        "estado":    "inscripcion_abierta",
        "plazas":    "10",
        "tipo_examen": "Concurso-oposición",
        "titulacion":  "Bachiller",
        "ultimo_scrape": "2025-01-01T00:00:00",
    }


@pytest.fixture
def repo_oferta():
    """Instancia del repositorio de ofertas para tests directos."""
    from app.repositories.oferta_repo import OfertaRepository
    return OfertaRepository()


@pytest.fixture
def repo_log():
    """Instancia del repositorio de logs para tests directos."""
    from app.repositories.log_repo import LogRepository
    return LogRepository()
