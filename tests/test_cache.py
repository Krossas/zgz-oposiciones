"""
tests/test_cache.py — Tests del módulo de caché.

Verifican que la caché almacena, devuelve y se invalida correctamente.
"""

import time
import pytest
from cachetools import TTLCache
from app.utils.cache import cached, invalidar_todo, cache_media, cache_larga


class TestCached:
    """Tests del decorador @cached."""

    def test_segunda_llamada_usa_cache(self):
        """La función decorada solo debe ejecutarse una vez si la clave no cambia."""
        llamadas = {"n": 0}
        cache_test = TTLCache(maxsize=10, ttl=60)

        @cached(cache_test, key_fn=lambda: "clave_fija")
        def funcion_costosa():
            llamadas["n"] += 1
            return "resultado"

        r1 = funcion_costosa()
        r2 = funcion_costosa()

        assert r1        == r2
        assert llamadas["n"] == 1   # Solo se ejecutó una vez

    def test_claves_distintas_no_interfieren(self):
        """Llamadas con claves diferentes deben cachearse por separado."""
        cache_test = TTLCache(maxsize=10, ttl=60)

        @cached(cache_test, key_fn=lambda x: f"key_{x}")
        def funcion(x):
            return x * 2

        assert funcion(3) == 6
        assert funcion(5) == 10
        assert len(cache_test) == 2

    def test_invalidar_todo_limpia_caches(self):
        """invalidar_todo debe vaciar todas las cachés globales."""
        # Poner algo en las cachés globales
        cache_media["test_key"]  = "valor_media"
        cache_larga["test_key2"] = "valor_larga"

        invalidar_todo()

        assert len(cache_media) == 0
        assert len(cache_larga) == 0

    def test_cache_expira_con_ttl(self):
        """Las entradas deben expirar después del TTL."""
        cache_rapida = TTLCache(maxsize=10, ttl=1)   # TTL de 1 segundo

        @cached(cache_rapida, key_fn=lambda: "k")
        def funcion():
            return time.time()

        t1 = funcion()
        time.sleep(1.1)   # Esperar a que expire
        t2 = funcion()

        assert t2 > t1   # Se volvió a ejecutar con un timestamp diferente
