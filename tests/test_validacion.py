"""
tests/test_validacion.py — Tests de las funciones de validación de parámetros.

Son los tests más rápidos y más importantes: validan que la capa de entrada
de la API rechaza correctamente los valores inválidos y acepta los válidos.
"""

import pytest
from app.utils.validacion import (
    ErrorValidacion,
    validar_anio, validar_grupo, validar_estado,
    validar_busqueda, validar_pagina, validar_por_pagina, validar_oferta_id
)


class TestValidarAnio:
    """Tests para la validación de años."""

    def test_anio_valido(self):
        assert validar_anio("2025") == 2025

    def test_anio_entero(self):
        assert validar_anio(2024) == 2024

    def test_anio_none_devuelve_none(self):
        assert validar_anio(None) is None

    def test_anio_vacio_devuelve_none(self):
        assert validar_anio("") is None

    def test_anio_texto_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="número entero"):
            validar_anio("veinte-veinticinco")

    def test_anio_fuera_de_rango_bajo(self):
        with pytest.raises(ErrorValidacion, match="rango"):
            validar_anio(1999)

    def test_anio_fuera_de_rango_alto(self):
        with pytest.raises(ErrorValidacion, match="rango"):
            validar_anio(2101)


class TestValidarGrupo:
    """Tests para la validación de grupos funcionariales."""

    @pytest.mark.parametrize("grupo", ["A1", "A2", "B", "C1", "C2", "E"])
    def test_grupos_validos(self, grupo):
        assert validar_grupo(grupo) == grupo

    def test_grupo_minusculas_se_normaliza(self):
        # Debe aceptar minúsculas normalizando a mayúsculas
        assert validar_grupo("c1") == "C1"

    def test_grupo_invalido_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="no válido"):
            validar_grupo("Z9")

    def test_grupo_none_devuelve_none(self):
        assert validar_grupo(None) is None


class TestValidarEstado:
    """Tests para la validación de estados de oferta."""

    def test_estado_valido(self):
        assert validar_estado("inscripcion_abierta") == "inscripcion_abierta"

    def test_estado_invalido_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="no válido"):
            validar_estado("activo")   # 'activo' no es un estado válido

    def test_estado_none_devuelve_none(self):
        assert validar_estado(None) is None


class TestValidarBusqueda:
    """Tests para la validación de textos de búsqueda."""

    def test_busqueda_valida(self):
        assert validar_busqueda("admin") == "admin"

    def test_busqueda_muy_corta_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="2 caracteres"):
            validar_busqueda("a")

    def test_busqueda_muy_larga_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="100 caracteres"):
            validar_busqueda("x" * 101)

    def test_busqueda_none_devuelve_none(self):
        assert validar_busqueda(None) is None

    def test_busqueda_vacia_devuelve_none(self):
        assert validar_busqueda("") is None


class TestValidarPaginacion:
    """Tests para la validación de parámetros de paginación."""

    def test_pagina_valida(self):
        assert validar_pagina("3") == 3

    def test_pagina_cero_lanza_error(self):
        with pytest.raises(ErrorValidacion):
            validar_pagina("0")

    def test_pagina_negativa_lanza_error(self):
        with pytest.raises(ErrorValidacion):
            validar_pagina("-1")

    def test_por_pagina_supera_maximo(self):
        with pytest.raises(ErrorValidacion, match="200"):
            validar_por_pagina("201")

    def test_por_pagina_none_devuelve_defecto(self):
        assert validar_por_pagina(None) == 100


class TestValidarOfertaId:
    """Tests para la validación de IDs de oferta."""

    def test_id_numerico_valido(self):
        assert validar_oferta_id("1739") == "1739"

    def test_id_con_letras_lanza_error(self):
        with pytest.raises(ErrorValidacion, match="número entero"):
            validar_oferta_id("abc")

    def test_id_vacio_lanza_error(self):
        with pytest.raises(ErrorValidacion):
            validar_oferta_id("")

    def test_id_demasiado_largo_lanza_error(self):
        with pytest.raises(ErrorValidacion):
            validar_oferta_id("12345678")   # Más de 6 dígitos
