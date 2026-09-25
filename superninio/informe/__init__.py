"""Diagnóstico explicativo y reporte PDF para el caficultor."""
from .diagnostico import diagnostico
from .pdf import generar_pdf

__all__ = ["diagnostico", "generar_pdf"]
