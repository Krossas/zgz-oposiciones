"""
utils/validacion.py — Validación de parámetros de entrada de la API.

Centraliza las reglas de validación para que las rutas sean limpias
y los errores al usuario sean claros y consistentes.

Por qué validar explícitamente:
  - SQLite con parámetros nombrados ya protege contra SQL injection,
    pero no valida que los tipos sean correctos
  - Un año como "abc" o un grupo como "Z99" no debería llegar al repositorio
  - Los mensajes de error de SQLite son técnicos; los nuestros deben ser útiles
"""

import re
from typing import Any, Optional


class ErrorValidacion(ValueError):
    """
    Excepción específica para errores de validación de parámetros.
    La capa de API la captura y devuelve HTTP 400 con el mensaje de error.
    """
    pass


# ── Grupos válidos del sistema de cuerpos de la Administración ────────────────
GRUPOS_VALIDOS = {"A1", "A2", "B", "C1", "C2", "E"}

# ── Estados válidos de una oferta ─────────────────────────────────────────────
ESTADOS_VALIDOS = {
    "inscripcion_abierta",
    "pendiente_inscripcion",
    "inscripcion_cerrada",
    "en_proceso",
    "bases_publicadas",
    "resuelto",
    "pendiente",
}


def validar_anio(valor: Any) -> Optional[int]:
    """
    Valida y convierte un parámetro de año.
    Acepta None (sin filtro) o un entero entre 2000 y 2100.
    """
    if valor is None or valor == "":
        return None
    try:
        anio = int(valor)
    except (ValueError, TypeError):
        raise ErrorValidacion(f"El parámetro 'anio' debe ser un número entero, no '{valor}'")

    if not (2000 <= anio <= 2100):
        raise ErrorValidacion(f"El año {anio} está fuera del rango válido (2000-2100)")

    return anio


def validar_grupo(valor: Any) -> Optional[str]:
    """
    Valida que el grupo sea uno de los valores oficiales.
    Acepta None (sin filtro).
    """
    if valor is None or valor == "":
        return None

    grupo = str(valor).strip().upper()
    if grupo not in GRUPOS_VALIDOS:
        raise ErrorValidacion(
            f"Grupo '{valor}' no válido. Valores permitidos: {', '.join(sorted(GRUPOS_VALIDOS))}"
        )
    return grupo


def validar_estado(valor: Any) -> Optional[str]:
    """
    Valida que el estado sea uno de los definidos en el sistema.
    Acepta None (sin filtro).
    """
    if valor is None or valor == "":
        return None

    estado = str(valor).strip().lower()
    if estado not in ESTADOS_VALIDOS:
        raise ErrorValidacion(
            f"Estado '{valor}' no válido. Valores permitidos: {', '.join(sorted(ESTADOS_VALIDOS))}"
        )
    return estado


def validar_busqueda(valor: Any) -> Optional[str]:
    """
    Valida y sanitiza un texto de búsqueda.
    - Longitud mínima de 2 caracteres para evitar búsquedas demasiado amplias
    - Longitud máxima de 100 caracteres
    - Elimina caracteres especiales de FTS5 que podrían causar errores de sintaxis
    """
    if valor is None or valor == "":
        return None

    texto = str(valor).strip()

    if len(texto) < 2:
        raise ErrorValidacion("La búsqueda debe tener al menos 2 caracteres")

    if len(texto) > 100:
        raise ErrorValidacion("La búsqueda no puede superar los 100 caracteres")

    return texto


def validar_pagina(valor: Any) -> int:
    """Valida el número de página para paginación. Mínimo 1."""
    if valor is None or valor == "":
        return 1
    try:
        pagina = int(valor)
    except (ValueError, TypeError):
        raise ErrorValidacion(f"El parámetro 'pagina' debe ser un número entero, no '{valor}'")

    if pagina < 1:
        raise ErrorValidacion("El número de página debe ser mayor o igual a 1")

    return pagina


def validar_por_pagina(valor: Any, maximo: int = 200) -> int:
    """
    Valida el número de resultados por página.
    Límite máximo para evitar consultas que devuelvan demasiados datos.
    """
    if valor is None or valor == "":
        return 100
    try:
        por_pagina = int(valor)
    except (ValueError, TypeError):
        raise ErrorValidacion(f"El parámetro 'por_pagina' debe ser un número entero, no '{valor}'")

    if por_pagina < 1:
        raise ErrorValidacion("'por_pagina' debe ser mayor o igual a 1")

    if por_pagina > maximo:
        raise ErrorValidacion(f"'por_pagina' no puede superar {maximo}")

    return por_pagina


def validar_oferta_id(valor: Any) -> str:
    """
    Valida que un oferta_id sea un número entero positivo (como string).
    Los IDs del Ayuntamiento son siempre números.
    """
    if not valor:
        raise ErrorValidacion("El ID de la oferta es obligatorio")

    if not re.match(r"^\d{1,6}$", str(valor)):
        raise ErrorValidacion(f"ID de oferta no válido: '{valor}'. Debe ser un número entero.")

    return str(valor)
