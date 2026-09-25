"""Eventos El Niño históricos y trayectoria del ONI para un escenario."""
from __future__ import annotations

from .climate import Oni, oni_at
from .stats import mean

SCENARIOS = {
    "moderado": {"label": "El Niño moderado", "peak": 1.2},
    "fuerte": {"label": "El Niño fuerte", "peak": 1.8},
    "super": {"label": "Superniño", "peak": 2.4},
}


def classify(peak: float) -> str:
    if peak >= 2.0:
        return "Superniño (muy fuerte)"
    if peak >= 1.5:
        return "Fuerte"
    if peak >= 1.0:
        return "Moderado"
    return "Débil"


def _flatten(oni: Oni) -> list[tuple[int, int, float]]:
    return [(y, m, v) for y in sorted(oni) for m, v in enumerate(oni[y]) if v is not None]


def find_el_nino_events(oni: Oni) -> list[dict]:
    """Definición operativa NOAA: ONI >= +0.5 durante >= 5 trimestres consecutivos."""
    s = _flatten(oni)
    events, i = [], 0
    while i < len(s):
        if s[i][2] >= 0.5:
            j = i
            while j + 1 < len(s) and s[j + 1][2] >= 0.5:
                j += 1
            if j - i + 1 >= 5:
                pk = max(range(i, j + 1), key=lambda k: (s[k][2], -k))
                y, m, v = s[pk]
                events.append({
                    "peak": v, "peak_y": y, "peak_m": m,
                    "year0": y if m >= 5 else y - 1,  # año de desarrollo del evento
                    "ongoing": j == len(s) - 1,
                    "class": classify(v),
                })
            i = j + 1
        else:
            i += 1
    return events


def oni_template(oni: Oni, min_peak: float = 1.5) -> dict:
    """Forma media normalizada del ONI de ene(-1) a dic(+1) (36 meses) de los eventos con pico >= min_peak."""
    evs = [e for e in find_el_nino_events(oni) if e["peak"] >= min_peak and not e["ongoing"]]
    shape, cnt = [0.0] * 36, [0] * 36
    for e in evs:
        for k in range(36):
            v = oni_at(oni, e["year0"] - 1, k)
            if v is None:
                continue
            shape[k] += v / e["peak"]
            cnt[k] += 1
    out = [shape[k] / cnt[k] if cnt[k] else 0.0 for k in range(36)]
    mx = max(out)
    return {"shape": [v / mx for v in out], "events": evs}


def scenario_trajectory(template: dict, peak: float, year0: int, start_y: int, start_m: int, months: int = 12) -> list[dict]:
    """12 meses {y, m, oni} desde (start_y, start_m) para un evento con año de desarrollo year0."""
    out = []
    for i in range(months):
        ab = start_y * 12 + start_m + i
        y, m = divmod(ab, 12)
        # El predictor de un mes m es el ONI centrado en m-1 (ver climate.build_dataset)
        k = (y - (year0 - 1)) * 12 + (m - 1)
        o = template["shape"][k] * peak if 0 <= k < 36 else 0.0
        out.append({"y": y, "m": m, "oni": o})
    return out


def mean_peak(events: list[dict]) -> float:
    return mean([e["peak"] for e in events])
