"""Carga de la serie ONI (NOAA CPC) desde oni.json. Se regenera con scripts/update_oni.py."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RUTA_ONI = Path(__file__).with_name("oni.json")


@lru_cache(maxsize=1)
def cargar_oni() -> tuple[dict[int, list[float | None]], dict]:
    """Devuelve (oni, meta). oni: {año: [12 valores DJF..NDJ]}; el valor i está centrado en el mes i."""
    data = json.loads(RUTA_ONI.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["oni"].items()}, data["meta"]
