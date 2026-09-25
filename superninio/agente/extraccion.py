"""Extracción de los datos de la finca desde el texto libre del caficultor.

ExtractorClaude: usa la API de Claude con salida estructurada (recomendado).
ExtractorReglas: expresiones regulares; respaldo cuando la API no está disponible y para pruebas.

Ambos implementan: extraer(texto, contexto) -> dict con las claves de CAMPOS (solo las encontradas).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Protocol

from pydantic import BaseModel, Field

from .disparador import normalizar

log = logging.getLogger(__name__)

CAMPOS = ("departamento", "municipio", "vereda", "lat", "lon", "edad_meses", "soqueado",
          "meses_desde_zoca", "nombre_finca", "cancelar")

DEPARTAMENTOS = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá", "Bolívar", "Boyacá", "Caldas", "Caquetá",
    "Casanare", "Cauca", "Cesar", "Chocó", "Córdoba", "Cundinamarca", "Guainía", "Guaviare", "Huila",
    "La Guajira", "Magdalena", "Meta", "Nariño", "Norte de Santander", "Putumayo", "Quindío", "Risaralda",
    "San Andrés", "Santander", "Sucre", "Tolima", "Valle del Cauca", "Vaupés", "Vichada",
]


class Extractor(Protocol):
    def extraer(self, texto: str, contexto: dict) -> dict: ...


class ExtraccionFinca(BaseModel):
    """Datos que el caficultor dijo explícitamente. null = no lo dijo."""

    departamento: Optional[str] = Field(None, description="Departamento de Colombia")
    municipio: Optional[str] = Field(None, description="Municipio donde está la finca")
    vereda: Optional[str] = Field(None, description="Vereda (sin la palabra 'vereda')")
    lat: Optional[float] = Field(None, description="Latitud decimal, solo si la escribió")
    lon: Optional[float] = Field(None, description="Longitud decimal, solo si la escribió")
    edad_meses: Optional[int] = Field(None, description="Edad del cafetal desde la siembra, en meses")
    soqueado: Optional[bool] = Field(None, description="true si el lote fue soqueado (zoca), false si dijo que no")
    meses_desde_zoca: Optional[int] = Field(None, description="Meses desde la última zoca")
    nombre_finca: Optional[str] = Field(None, description="Nombre de la finca")
    cancelar: bool = Field(False, description="true si quiere salir o cancelar el diagnóstico")


SISTEMA = """Eres el extractor de datos del diagnóstico Superniño de AMY, un asistente por WhatsApp para caficultores de Colombia.
Recibes UN mensaje del caficultor y devuelves solo los datos que dijo de forma explícita. Nunca inventes ni supongas.

Reglas:
- Duraciones siempre en meses: "3 años" = 36, "año y medio" = 18, "medio año" = 6, "8 meses" = 8.
- edad_meses es la edad del cafetal desde la siembra. meses_desde_zoca es el tiempo desde la última zoca.
- Zoca, soca, soqueo, zoqueado, soqueé, recepa: significan que el lote fue soqueado (soqueado = true).
  "No lo he soqueado", "nunca", "es siembra nueva", "renové sembrando": soqueado = false.
- Si responde con algo corto ("sí", "no", "3", "hace un año"), interprétalo según la última pregunta que se le hizo (viene en el contexto).
- Ubicación: vereda, municipio y departamento tal como los escribe, corrigiendo solo tildes y mayúsculas. lat/lon solo si escribió coordenadas numéricas.
- Si no sabe un dato o no lo mencionó, déjalo en null.
- cancelar = true solo si claramente quiere salir o detener el diagnóstico."""


class ExtractorClaude:
    """Extracción con Claude (salida estructurada validada con Pydantic)."""

    def __init__(self, client=None, model: str | None = None, respaldo: Extractor | None = None):
        import anthropic  # dependencia opcional: solo si se usa este extractor

        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic()
        self.model = model or os.environ.get("SUPERNINIO_MODELO", "claude-opus-5")
        self.respaldo = respaldo or ExtractorReglas()

    def extraer(self, texto: str, contexto: dict) -> dict:
        conocido = {k: v for k, v in (contexto.get("datos") or {}).items() if v is not None}
        usuario = (f"Datos ya conocidos: {json.dumps(conocido, ensure_ascii=False)}\n"
                   f"Última pregunta hecha: {contexto.get('ultima_pregunta') or 'ninguna'}\n\n"
                   f"Mensaje del caficultor:\n{texto}")
        a = self._anthropic
        try:
            resp = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=4000,
                system=SISTEMA,
                messages=[{"role": "user", "content": usuario}],
                output_format=ExtraccionFinca,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (a.RateLimitError, a.APIConnectionError, a.APIStatusError) as e:
            log.warning("Extracción con Claude falló (%s); uso reglas", type(e).__name__)
            return self.respaldo.extraer(texto, contexto)
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            log.warning("Extracción sin resultado (stop_reason=%s); uso reglas", resp.stop_reason)
            return self.respaldo.extraer(texto, contexto)
        out = {k: v for k, v in resp.parsed_output.model_dump().items() if v is not None}
        if not out.get("cancelar"):
            out.pop("cancelar", None)
        return out


# ---------------------------------------------------------------- respaldo por reglas
_NUM_PALABRA = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
                "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20}
_NUM = r"(\d+(?:[.,]\d+)?|" + "|".join(_NUM_PALABRA) + r")"
_DUR = re.compile(_NUM + r"\s*(anos?|mes(?:es)?)(\s+y\s+medio)?")
_ZOCA = re.compile(r"(soq|zoq|zoca|soca|recep)")
_NEG_ZOCA = re.compile(r"\b(no|nunca|sin|jamas)\b[^.;\n]{0,25}(soq|zoq|zoca|soca|recep)|siembra nueva|renove sembrando")
_COORD = re.compile(r"(-?\d{1,2}\.\d{2,})\s*[,; ]\s*(-?\d{2,3}\.\d{2,})")
_LUGAR_FIN = r"(?=\s*(?:[,.;\n]|$|\bdel?\b|\ben\b|\bmunicipio\b|\bdepartamento\b|\btiene\b|\by\b))"
_VEREDA = re.compile(r"vereda\s+([a-z][a-z ]{1,40}?)" + _LUGAR_FIN)
_MUNICIPIO = re.compile(r"municipio(?:\s+de)?\s+([a-z][a-z ]{1,40}?)" + _LUGAR_FIN)
_EN_LUGAR = re.compile(r"\ben\s+([a-z][a-z ]{1,40}?)" + _LUGAR_FIN)
_NO_LUGAR = re.compile(r"^(la finca|el lote|la vereda|vereda|el municipio|municipio|el cafetal|mi finca)\b")


def _meses(m: re.Match) -> int:
    n = m.group(1)
    v = _NUM_PALABRA[n] if n in _NUM_PALABRA else float(n.replace(",", "."))
    anios = m.group(2).startswith("ano")
    total = v * 12 if anios else v
    if m.group(3) and anios:
        total += 6
    return int(round(total))


def _titulo(s: str) -> str:
    return " ".join(w if i and w in ("de", "del", "la", "las", "los", "el") else w.capitalize()
                    for i, w in enumerate(s.split()))


class ExtractorReglas:
    """Extracción básica por patrones. Cubre mensajes simples; el extractor con LLM cubre el resto."""

    def extraer(self, texto: str, contexto: dict) -> dict:
        t = normalizar(texto)
        out: dict = {}
        ultima = contexto.get("ultima_pregunta") or ""

        c = _COORD.search(t)
        if c:
            out["lat"], out["lon"] = float(c.group(1)), float(c.group(2))

        # Duraciones: las que siguen a una mención de zoca son tiempo desde la zoca; las demás, edad.
        zoca_pos = [m.start() for m in _ZOCA.finditer(t)]
        for m in _DUR.finditer(t):
            antes = t[max(0, m.start() - 35):m.start()]
            es_zoca = any(0 <= m.start() - p <= 35 for p in zoca_pos) and ("hace" in antes or "tiene" not in antes)
            if es_zoca and "meses_desde_zoca" not in out:
                out["meses_desde_zoca"] = _meses(m)
            elif not es_zoca and "edad_meses" not in out:
                out["edad_meses"] = _meses(m)

        if _NEG_ZOCA.search(t):
            out["soqueado"] = False
        elif zoca_pos:
            out["soqueado"] = True
        elif ultima == "soqueado":
            if re.match(r"^\W*(si|claro|asi es|correcto)\b", t):
                out["soqueado"] = True
            elif re.match(r"^\W*(no|nunca)\b", t):
                out["soqueado"] = False
        if ultima == "meses_desde_zoca" and "meses_desde_zoca" in out and "edad_meses" in out:
            out.pop("edad_meses")
        if ultima == "meses_desde_zoca" and "edad_meses" in out and "meses_desde_zoca" not in out:
            out["meses_desde_zoca"] = out.pop("edad_meses")

        v = _VEREDA.search(t)
        if v:
            out["vereda"] = _titulo(v.group(1).strip())
        mu = _MUNICIPIO.search(t) or next((m for m in _EN_LUGAR.finditer(t) if not _NO_LUGAR.match(m.group(1))), None)
        if mu:
            out["municipio"] = _titulo(mu.group(1).strip())
        for d in DEPARTAMENTOS:
            if re.search(r"\b" + normalizar(d) + r"\b", t):
                out["departamento"] = d
                break
        # Respuesta corta a la pregunta de ubicación: "La Floresta, Chinchiná, Caldas"
        if ultima == "ubicacion" and "municipio" not in out and not c:
            partes = [p.strip() for p in re.split(r"[,\n]", t) if p.strip() and not _DUR.search(p)]
            partes = [p for p in partes if normalizar(out.get("departamento", "-")) != p]
            if partes and len(partes) <= 3:
                out["municipio"] = _titulo(partes[-1].replace("vereda", "").strip())
                if len(partes) >= 2 and "vereda" not in out:
                    out["vereda"] = _titulo(partes[0].replace("vereda", "").strip())
        if re.match(r"^\W*(cancelar|salir)\b", t):
            out["cancelar"] = True
        return out
