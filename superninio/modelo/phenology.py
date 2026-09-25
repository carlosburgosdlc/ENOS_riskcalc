"""Fenología del café arábica y sensibilidad a déficit hídrico (Sd) y calor (Sh) por mes.

Pesos 0-1: síntesis de literatura, NO estimados estadísticamente:
 - Camargo & Camargo (2001) Bragantia 60(1): fases fenológicas del café arábica.
 - DaMatta & Ramalho (2006) Braz. J. Plant Physiol. 18(1): sequía y temperatura en café.
 - Arcila et al. (2007) Cenicafé: ciclo floración-cosecha ~32 semanas; cosecha según latitud.
 - Jaramillo et al. (2009, 2011) PLoS ONE: temperatura y broca (Hypothenemus hampei).
"""
from __future__ import annotations

from typing import Sequence

MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MONTHS_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]

# Etapas reproductivas relativas al mes de floración F (desfase en meses).
REPRO = [
    {"from": -2, "to": -1, "name": "Diferenciación floral", "Sd": 0.3, "Sh": 0.4},
    {"from": 0, "to": 0, "name": "Floración", "Sd": 0.85, "Sh": 0.9},
    {"from": 1, "to": 3, "name": "Expansión del fruto", "Sd": 1.0, "Sh": 0.6},
    {"from": 4, "to": 5, "name": "Llenado del grano", "Sd": 0.9, "Sh": 0.75},
    {"from": 6, "to": 8, "name": "Maduración y cosecha", "Sd": 0.45, "Sh": 0.8},
]
VEGETATIVE = {"name": "Crecimiento vegetativo", "Sd": 0.35, "Sh": 0.3}

JUVENILE = [
    {"max": 6, "name": "Establecimiento", "Sd": 1.0, "Sh": 0.6},
    {"max": 18, "name": "Levante (sin producción)", "Sd": 0.75, "Sh": 0.45},
]
ZOCA = [
    {"max": 6, "name": "Rebrote de zoca", "Sd": 0.55, "Sh": 0.4},
    {"max": 18, "name": "Desarrollo de chupones", "Sd": 0.5, "Sh": 0.35},
]
FIRST_HARVEST_MONTHS = 18
FLOWER_TO_HARVEST = 8  # meses (~32 semanas)

# Patrones de cosecha: mes pico de cosecha (0-11) y peso relativo del ciclo.
HARVEST_PATTERNS = {
    "norte": {"label": "Una cosecha principal (oct-dic)", "cycles": [{"harvest": 10, "w": 1.0}]},
    "centro": {"label": "Principal oct-dic y mitaca abr-jun", "cycles": [{"harvest": 10, "w": 1.0}, {"harvest": 4, "w": 0.6}]},
    "sur": {"label": "Principal abr-jun y traviesa oct-dic", "cycles": [{"harvest": 5, "w": 1.0}, {"harvest": 10, "w": 0.5}]},
}


def pattern_from_latitude(lat: float) -> str:
    """Aproximación por latitud (Arcila et al. 2007): norte >7°N, centro 3.5-7°N, sur <3.5°N."""
    if lat >= 7:
        return "norte"
    if lat >= 3.5:
        return "centro"
    return "sur"


def _repro_stage(cal_month: int, cycles: Sequence[dict]) -> dict:
    best = dict(VEGETATIVE)
    for c in cycles:
        F = (c["harvest"] - FLOWER_TO_HARVEST + 12) % 12
        off = (cal_month - F + 12) % 12
        if off > 8:
            off -= 12  # -3..8
        st = next((s for s in REPRO if s["from"] <= off <= s["to"]), None)
        if st is None:
            continue
        Sd = max(VEGETATIVE["Sd"], st["Sd"] * c["w"])
        Sh = max(VEGETATIVE["Sh"], st["Sh"] * c["w"])
        if Sd + Sh > best["Sd"] + best["Sh"]:
            best = {"name": st["name"] + (" (mitaca/traviesa)" if c["w"] < 1 else ""), "Sd": Sd, "Sh": Sh}
    return best


def altitude_heat_factor(elev: float | None) -> float:
    """Cafetales bajos operan más cerca del límite térmico del arábica."""
    if elev is None:
        return 1.0
    if elev < 1300:
        return 1.25
    if elev > 1700:
        return 0.85
    return 1.0


def sensitivity_calendar(crop: dict, months: Sequence[dict]) -> list[dict]:
    """crop: {ageMonths, zoca, monthsSinceZoca, pattern, elevation}; months: [{y, m}].
    Devuelve por mes {y, m, age, stage, Sd, Sh}."""
    cycles = HARVEST_PATTERNS[crop["pattern"]]["cycles"]
    hf = altitude_heat_factor(crop.get("elevation"))
    zoca = crop["zoca"]
    out = []
    for i, mo in enumerate(months):
        age = (crop["monthsSinceZoca"] if zoca else crop["ageMonths"]) + i + 1
        table = ZOCA if zoca else JUVENILE
        mod = 1.0
        if age < FIRST_HARVEST_MONTHS:
            st = next((s for s in table if age < s["max"]), table[-1])
        else:
            st = _repro_stage(mo["m"], cycles)
            if not zoca and age < 30:
                mod = 1.1  # primer año productivo: raíces aún superficiales
            if (not zoca and age > 84) or (zoca and age > 60):
                mod = 1.1  # cafetal envejecido: menor vigor
        out.append({
            "y": mo["y"], "m": mo["m"], "age": age, "stage": st["name"],
            "Sd": min(1.0, st["Sd"] * mod),
            "Sh": min(1.0, st["Sh"] * mod * hf),
        })
    return out


def crop_diagnosis(crop: dict) -> list[str]:
    notes = []
    if crop["zoca"]:
        if crop["monthsSinceZoca"] > 60:
            notes.append("Han pasado más de 5 años desde la zoca: la productividad va en declive; planifique la renovación.")
    elif crop["ageMonths"] > 84:
        notes.append("Cafetal de más de 7 años sin zoca: vigor reducido. La renovación es prioritaria, pero evite hacerla justo antes de los meses de mayor riesgo.")
    elev = crop.get("elevation")
    if elev is not None and (elev < 1000 or elev > 2300):
        notes.append(f"Altitud de {round(elev)} m, fuera de la franja típica del café en Colombia (1000-2300 m): interprete con cautela.")
    return notes
