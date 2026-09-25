"""Detección de la palabra clave que activa el subagente y de la intención de cancelar."""
from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes (ñ -> n)."""
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# superniño, super niño, súper-niño, SUPERNIÑO, superninio, super nino...
_DISPARADOR = re.compile(r"\bsuper\W{0,2}nin?i?os?\b")
_CANCELAR = re.compile(r"^\W*(cancelar|cancela|salir|terminar|parar|stop)\b")


def es_disparador(texto: str | None) -> bool:
    return bool(texto) and bool(_DISPARADOR.search(normalizar(texto)))


def es_cancelacion(texto: str | None) -> bool:
    return bool(texto) and bool(_CANCELAR.search(normalizar(texto.strip())))


def quitar_disparador(texto: str) -> str:
    """Texto sin la palabra clave, para extraer datos que vengan en el mismo mensaje."""
    return _DISPARADOR.sub(" ", normalizar(texto)).strip()
