"""Subagente de WhatsApp: se activa con "Superniño", pide los datos, calcula y responde con un PDF."""
from .conversacion import AlmacenMemoria, Respuesta, SubagenteSuperninio
from .disparador import es_cancelacion, es_disparador
from .extraccion import ExtractorClaude, ExtractorReglas

__all__ = ["SubagenteSuperninio", "Respuesta", "AlmacenMemoria", "ExtractorClaude", "ExtractorReglas",
           "es_disparador", "es_cancelacion"]
