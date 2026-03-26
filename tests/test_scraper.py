"""
tests/test_scraper.py — Tests del servicio de scraping.

No testean la conexión real a zaragoza.es (eso requeriría internet
y haría los tests lentos e inestables). En su lugar, testean las
funciones de parsing y detección de estado con datos de ejemplo
que reproducen el formato real de la web.
"""

import pytest
from datetime import datetime, timedelta


class TestDetectarEstado:
    """Tests de la función _detectar_estado del scraper."""

    def _hacer_anuncio(self, texto, fecha=None):
        """Helper para crear un anuncio de prueba."""
        return {"texto": texto, "fecha": fecha, "url": None}

    def test_inscripcion_abierta_cuando_plazo_activo(self):
        """Si hoy está dentro del plazo, el estado debe ser inscripcion_abierta."""
        from app.services.scraper import _detectar_estado

        hoy    = datetime.now()
        inicio = (hoy - timedelta(days=5)).strftime("%d/%m/%Y")
        fin    = (hoy + timedelta(days=10)).strftime("%d/%m/%Y")

        datos = {"anuncios": [self._hacer_anuncio(
            f"Presentación de instancias (plazo del {inicio} al {fin}, ambos inclusive)"
        )]}
        assert _detectar_estado(datos) == "inscripcion_abierta"

    def test_inscripcion_cerrada_cuando_plazo_pasado(self):
        """Si el plazo ya terminó y no hay más anuncios, estado inscripcion_cerrada."""
        from app.services.scraper import _detectar_estado

        datos = {"anuncios": [self._hacer_anuncio(
            "Presentación de instancias (plazo del 01/01/2020 al 15/01/2020, ambos inclusive)"
        )]}
        assert _detectar_estado(datos) == "inscripcion_cerrada"

    def test_en_proceso_cuando_hay_lista_admitidos(self):
        """Si el plazo pasó y hay anuncio de lista de admitidos, estado en_proceso."""
        from app.services.scraper import _detectar_estado

        datos = {"anuncios": [
            self._hacer_anuncio("Presentación de instancias (plazo del 01/01/2020 al 15/01/2020)"),
            self._hacer_anuncio("Lista provisional de admitidos y excluidos"),
        ]}
        assert _detectar_estado(datos) == "en_proceso"

    def test_resuelto_cuando_hay_resolucion_definitiva(self):
        """Si hay anuncio de resolución definitiva, estado resuelto."""
        from app.services.scraper import _detectar_estado

        datos = {"anuncios": [
            self._hacer_anuncio("Bases de la convocatoria"),
            self._hacer_anuncio("Resolución definitiva y nombramiento"),
        ]}
        assert _detectar_estado(datos) == "resuelto"

    def test_bases_publicadas_solo_con_bases(self):
        """Si solo hay bases publicadas, estado bases_publicadas."""
        from app.services.scraper import _detectar_estado

        datos = {"anuncios": [self._hacer_anuncio("Bases de la convocatoria")]}
        assert _detectar_estado(datos) == "bases_publicadas"

    def test_pendiente_sin_anuncios(self):
        """Sin anuncios, el estado debe ser pendiente."""
        from app.services.scraper import _detectar_estado

        assert _detectar_estado({"anuncios": []}) == "pendiente"
        assert _detectar_estado({})               == "pendiente"

    def test_pendiente_inscripcion_cuando_plazo_futuro(self):
        """Si el plazo aún no ha comenzado, estado pendiente_inscripcion."""
        from app.services.scraper import _detectar_estado

        hoy    = datetime.now()
        inicio = (hoy + timedelta(days=10)).strftime("%d/%m/%Y")
        fin    = (hoy + timedelta(days=25)).strftime("%d/%m/%Y")

        datos = {"anuncios": [self._hacer_anuncio(
            f"Presentación de instancias (plazo del {inicio} al {fin})"
        )]}
        assert _detectar_estado(datos) == "pendiente_inscripcion"


class TestLimpiarTexto:
    """Tests de la función auxiliar _limpiar_texto del scraper."""

    def test_elimina_espacios_extra(self):
        from app.services.scraper import _limpiar_texto
        assert _limpiar_texto("  hola   mundo  ") == "hola mundo"

    def test_elimina_saltos_de_linea(self):
        from app.services.scraper import _limpiar_texto
        assert _limpiar_texto("hola\nmundo\n") == "hola mundo"

    def test_none_devuelve_none(self):
        from app.services.scraper import _limpiar_texto
        assert _limpiar_texto(None) is None

    def test_vacio_devuelve_none(self):
        from app.services.scraper import _limpiar_texto
        assert _limpiar_texto("   ") is None


class TestExtractoresPDF:
    """Tests del servicio de lectura de PDFs."""

    TEXTO_PDF_EJEMPLO = """
BASES DE LA CONVOCATORIA

Requisitos de participación
Los aspirantes deberán estar en posesión del título de Bachiller o equivalente.

Sistema de selección y puntuación
Fase de oposición: hasta 60 puntos.
Fase de concurso: hasta 40 puntos. Total máximo: 100 puntos.

TEMARIO

Tema 1. La Constitución Española de 1978. Estructura y principios fundamentales.
Tema 2. Los derechos fundamentales y las libertades públicas.
Tema 3. La organización territorial del Estado. Las Comunidades Autónomas.
Tema 4. La Unión Europea. Instituciones y competencias principales.
Tema 5. El Estatuto de Autonomía de Aragón.

Fecha de examen prevista: 15/06/2026.
Plazo de instancias: del 01/03/2026 al 20/03/2026.
"""

    def test_extrae_temario(self):
        from app.services.pdf_service import _extraer_temario
        temas = _extraer_temario(self.TEXTO_PDF_EJEMPLO)
        assert len(temas) == 5
        assert temas[0]["numero"] == 1
        assert "Constitución" in temas[0]["texto"]

    def test_extrae_puntuacion(self):
        from app.services.pdf_service import _extraer_puntuacion
        puntuacion = _extraer_puntuacion(self.TEXTO_PDF_EJEMPLO)
        assert puntuacion is not None
        assert "60" in puntuacion or "40" in puntuacion

    def test_extrae_requisitos(self):
        from app.services.pdf_service import _extraer_requisitos
        requisitos = _extraer_requisitos(self.TEXTO_PDF_EJEMPLO)
        assert requisitos is not None
        assert "Bachiller" in requisitos

    def test_extrae_fechas(self):
        from app.services.pdf_service import _extraer_fechas
        fechas = _extraer_fechas(self.TEXTO_PDF_EJEMPLO)
        assert "15/06/2026" in fechas
        assert "01/03/2026" in fechas

    def test_pdf_sin_texto_devuelve_advertencia(self):
        from app.services.pdf_service import _extraer_contenido_pdf
        import io

        # Crear un PDF mínimo válido pero sin contenido de texto
        pdf_vacio_bytes = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
        resultado = _extraer_contenido_pdf(pdf_vacio_bytes, "test.pdf")
        # Un PDF sin texto debe devolver advertencia o lista vacía de temas
        assert resultado is not None
        assert resultado["temario"] == [] or resultado.get("advertencia") is not None
