"""Agregación de clima diario a mensual y construcción de la base de regresión."""
from __future__ import annotations

import calendar
from typing import Mapping, Sequence

from .stats import mean, sd

REF_START = 1991  # normal climatológica OMM 1991-2020
REF_END = 2020
MIN_DAY_FRACTION = 0.9
VARS = ("D3", "Tmax", "P")

Oni = Mapping[int, Sequence[float | None]]


def daily_to_monthly(daily: Mapping[str, Sequence]) -> list[dict]:
    """daily: {'time': ['1950-01-01', ...], 'precipitation_sum': [...],
    'et0_fao_evapotranspiration': [...], 'temperature_2m_max': [...]} -> [{'y','m','P','ET0','Tmax'}].

    Un mes con menos del 90 % de días válidos se descarta (valores None); si faltan pocos días,
    las sumas se escalan para no sesgar el mes.
    """
    acc: dict[tuple[int, int], list] = {}
    P, E, T = daily["precipitation_sum"], daily["et0_fao_evapotranspiration"], daily["temperature_2m_max"]
    for i, fecha in enumerate(daily["time"]):
        y, m = int(fecha[:4]), int(fecha[5:7]) - 1
        a = acc.setdefault((y, m), [0.0, 0.0, 0.0, 0, 0, 0])
        if P[i] is not None:
            a[0] += P[i]; a[3] += 1
        if E[i] is not None:
            a[1] += E[i]; a[4] += 1
        if T[i] is not None:
            a[2] += T[i]; a[5] += 1
    out = []
    for (y, m), (p, e, t, n_p, n_e, n_t) in sorted(acc.items()):
        days = calendar.monthrange(y, m + 1)[1]
        ok = min(n_p, n_e, n_t) >= MIN_DAY_FRACTION * days
        out.append({
            "y": y, "m": m,
            "P": p * days / n_p if ok else None,
            "ET0": e * days / n_e if ok else None,
            "Tmax": t / n_t if ok else None,
        })
    return out


def oni_at(oni: Oni, y: int, m: int) -> float | None:
    """ONI del trimestre centrado en el mes m del año y (m puede salirse de 0-11)."""
    yy, mm = y + m // 12, m % 12
    row = oni.get(yy)
    return row[mm] if row is not None and row[mm] is not None else None


def build_dataset(monthly: Sequence[Mapping], oni: Oni) -> dict:
    """Por mes calendario, filas {year, oni, D3, Tmax, P, zD3, zT, zP}.

    D3: balance hídrico P - ET0 acumulado en 3 meses (m-2..m), tipo SPEI-3.
    Predictor: ONI del trimestre centrado en m-1 (el mismo trimestre m-2..m).
    Estandarización por mes calendario contra la normal 1991-2020.
    """
    by_key = {r["y"] * 12 + r["m"]: r for r in monthly}
    rows: list[list[dict]] = [[] for _ in range(12)]
    for r in monthly:
        k = r["y"] * 12 + r["m"]
        w = [by_key.get(k - 2), by_key.get(k - 1), r]
        if any(x is None or x["P"] is None for x in w):
            continue
        o = oni_at(oni, r["y"], r["m"] - 1)
        if o is None:
            continue
        rows[r["m"]].append({
            "year": r["y"], "oni": o,
            "D3": sum(x["P"] - x["ET0"] for x in w),
            "Tmax": r["Tmax"], "P": r["P"],
        })
    clim = []
    for lst in rows:
        ref = [r for r in lst if REF_START <= r["year"] <= REF_END]
        base = ref if len(ref) >= 20 else lst
        clim.append({v: {"mean": mean([r[v] for r in base]), "sd": sd([r[v] for r in base])} for v in VARS})
    for m, lst in enumerate(rows):
        c = clim[m]
        for r in lst:
            r["zD3"] = (r["D3"] - c["D3"]["mean"]) / c["D3"]["sd"]
            r["zT"] = (r["Tmax"] - c["Tmax"]["mean"]) / c["Tmax"]["sd"]
            r["zP"] = (r["P"] - c["P"]["mean"]) / c["P"]["sd"]
    return {"rows": rows, "clim": clim}
