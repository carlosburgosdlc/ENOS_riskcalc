"""Geocodificación de vereda / municipio con Nominatim (OpenStreetMap).

Política de uso de Nominatim: máximo 1 solicitud por segundo y un User-Agent identificable.
Configure NOMINATIM_USER_AGENT (p. ej. "SUA-AMY/1.0 (contacto@empresa.com)").
Para alto volumen, use una instancia propia o un proveedor comercial.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

NOMINATIM = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
_ultimo = 0.0


@dataclass
class Lugar:
    lat: float
    lon: float
    precision: str  # "vereda" | "municipio"
    nombre: str


def _buscar(q: str, **extra) -> list[dict]:
    global _ultimo
    espera = 1.0 - (time.monotonic() - _ultimo)
    if espera > 0:
        time.sleep(espera)
    params = {"format": "jsonv2", "countrycodes": "co", "limit": "5", "accept-language": "es", "q": q, **extra}
    ua = os.environ.get("NOMINATIM_USER_AGENT", "superninio/1.0")
    req = urllib.request.Request(f"{NOMINATIM}/search?{urllib.parse.urlencode(params)}", headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001 - la geocodificación es opcional: el agente pide otro dato
        return []
    finally:
        _ultimo = time.monotonic()


def geocodificar(municipio: str, departamento: str | None = None, vereda: str | None = None) -> Lugar | None:
    """Ubica la vereda (si OSM la tiene) o, si no, el centro del municipio. None si no encuentra nada."""
    consulta = ", ".join(x for x in (municipio, departamento, "Colombia") if x)
    res = _buscar(consulta)
    if not res:
        return None
    m = res[0]
    if vereda:
        s, n, w, e = (float(v) for v in m["boundingbox"])
        viewbox = f"{w},{n},{e},{s}"
        for q in (f"{vereda}, {municipio}", f"vereda {vereda}", vereda):
            rv = _buscar(q, viewbox=viewbox, bounded="1")
            if rv:
                return Lugar(float(rv[0]["lat"]), float(rv[0]["lon"]), "vereda", rv[0]["display_name"])
    return Lugar(float(m["lat"]), float(m["lon"]), "municipio", m["display_name"])
