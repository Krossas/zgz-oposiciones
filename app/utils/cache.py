"""
utils/cache.py — Caché de respuestas de la API.

Usa cachetools.TTLCache: un dict con tiempo de vida máximo (TTL).
Cuando una entrada supera su TTL, se elimina automáticamente en el
siguiente acceso.

Por qué caché aquí:
  - /api/frecuencia hace un GROUP BY sobre toda la tabla histórica
  - /api/estadisticas agrega varias tablas
  - Estos datos no cambian entre scrapings, pero se consultan
    cada vez que el frontend hace polling o cambia de pestaña
  - Con caché, estas consultas costosas solo se ejecutan una vez
    por ventana de tiempo, no en cada petición

El decorador @invalidar_al_scrapear permite borrar la caché
cuando termina un scraping (para que los datos sean frescos).
"""

import logging
from functools import wraps

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ── Instancias de caché ────────────────────────────────────────────────────────
# TTLCache(maxsize, ttl): máximo N entradas, cada una válida TTL segundos

# Caché corta: estado del sistema (se actualiza cada pocos segundos en polling)
cache_estado = TTLCache(maxsize=1,   ttl=5)

# Caché media: estadísticas y listas que cambian solo al scrapear
cache_media  = TTLCache(maxsize=20,  ttl=300)   # 5 minutos

# Caché larga: datos históricos (frecuencia, cuadros anuales) que raramente cambian
cache_larga  = TTLCache(maxsize=50,  ttl=3600)  # 1 hora

# Registro de todas las cachés para poder limpiarlas a la vez
_todas_las_caches = [cache_estado, cache_media, cache_larga]


def invalidar_todo():
    """
    Borra todas las cachés.
    Se llama cuando termina un scraping para forzar datos frescos.
    """
    for cache in _todas_las_caches:
        cache.clear()
    logger.info("Cachés invalidadas")


def cached(cache: TTLCache, key_fn=None):
    """
    Decorador que cachea el resultado de una función.

    Args:
        cache:  Instancia de TTLCache a usar
        key_fn: Función que genera la clave de caché a partir de los argumentos.
                Por defecto usa el nombre de la función + sus argumentos.

    Uso:
        @cached(cache_larga)
        def obtener_frecuencia(self):
            ...

        @cached(cache_media, key_fn=lambda self, anio: f"anuales_{anio}")
        def obtener_anuales(self, anio):
            ...
    """
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché
            if key_fn:
                clave = key_fn(*args, **kwargs)
            else:
                clave = f"{func.__qualname__}_{args[1:]}_{kwargs}"

            # Intentar devolver desde caché
            if clave in cache:
                logger.debug("Cache HIT: %s", clave)
                return cache[clave]

            # Calcular y guardar en caché
            logger.debug("Cache MISS: %s", clave)
            resultado    = func(*args, **kwargs)
            cache[clave] = resultado
            return resultado

        return wrapper
    return decorador
