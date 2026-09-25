"""Modelo de amenaza condicionado a ENOS e Índice de Riesgo Climático para Café (IRCC).

Para cada mes calendario m y variable estandarizada z (D3 = balance hídrico 3 meses, Tmax):
    z = b0 + b1·ONI + b2·(año - 2000)/10 + e
b1 = señal ENOS local; b2 = tendencia (separa el calentamiento de El Niño).
P(mes seco) = P(z_D3 < -0.8416) y P(mes caliente) = P(z_T > +0.8416) (percentiles 20/80), con la
distribución empírica de residuos inflada por la incertidumbre de parámetros sqrt(n/df·(1+h0)).
Incertidumbre del índice: bootstrap de años completos.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .stats import OLS, benjamini_hochberg, leverage, quantile, rng

Z20 = 0.8416  # cuantil 80 de la normal estándar
FIT_VARS = ("zD3", "zT", "zP")


def _design(oni: float, year: int) -> list[float]:
    return [1.0, oni, (year - 2000) / 10]


class _MonthData:
    """Filas de un mes calendario en arreglos numpy, indexables por año."""

    def __init__(self, rows: Sequence[dict]):
        self.years = [r["year"] for r in rows]
        self.pos = {y: i for i, y in enumerate(self.years)}
        self.X = np.array([_design(r["oni"], r["year"]) for r in rows], dtype=float)
        self.y = {v: np.array([r[v] for r in rows], dtype=float) for v in FIT_VARS}

    def fit(self, v: str, idx: np.ndarray | None = None) -> OLS:
        if idx is None:
            return OLS(self.X, self.y[v])
        return OLS(self.X[idx], self.y[v][idx])


def exceed_prob(fit: OLS, x0: Sequence[float], direction: int) -> float:
    """Probabilidad de cruzar el umbral: direction=-1 (z < -Z20) o +1 (z > +Z20)."""
    mu = float(np.dot(x0, fit.beta))
    infl = math.sqrt((fit.n / fit.df) * (1 + leverage(fit.xtx_inv, x0)))
    z = mu + fit.resid * infl
    hits = (z < -Z20) if direction < 0 else (z > Z20)
    return float(hits.sum()) / len(fit.resid)


def irc(calendar: Sequence[dict], pd: Sequence[float], ph: Sequence[float]) -> float:
    num = sum(c["Sd"] * pd[i] + c["Sh"] * ph[i] for i, c in enumerate(calendar))
    den = sum(c["Sd"] + c["Sh"] for c in calendar)
    return 100 * num / den


def category(v: float) -> dict:
    if v < 25:
        return {"key": "bajo", "label": "Bajo"}
    if v < 35:
        return {"key": "moderado", "label": "Moderado"}
    if v < 50:
        return {"key": "alto", "label": "Alto"}
    return {"key": "muyalto", "label": "Muy alto"}


def _month_probs(fits: Sequence[dict], trajectory: Sequence[dict]) -> dict:
    out = {"pdS": [], "phS": [], "pdN": [], "phN": []}
    for t in trajectory:
        f = fits[t["m"]]
        xs, xn = _design(t["oni"], t["y"]), _design(0.0, t["y"])
        out["pdS"].append(exceed_prob(f["zD3"], xs, -1))
        out["phS"].append(exceed_prob(f["zT"], xs, +1))
        out["pdN"].append(exceed_prob(f["zD3"], xn, -1))
        out["phN"].append(exceed_prob(f["zT"], xn, +1))
    return out


def compute_risk(dataset: dict, trajectory: Sequence[dict], calendar: Sequence[dict],
                 B: int = 1000, seed: int = 20260922) -> dict:
    rows, clim = dataset["rows"], dataset["clim"]
    md = [_MonthData(r) for r in rows]
    fits = [{v: d.fit(v) for v in FIT_VARS} for d in md]
    pr = _month_probs(fits, trajectory)
    irc_s = irc(calendar, pr["pdS"], pr["phS"])
    irc_n = irc(calendar, pr["pdN"], pr["phN"])

    # Significancia de la señal ENOS por mes (pendiente b1), con control FDR (Benjamini-Hochberg).
    pD = [float(f["zD3"].p[1]) for f in fits]
    pT = [float(f["zT"].p[1]) for f in fits]
    q = benjamini_hochberg(pD + pT)
    qD, qT = q[:12], q[12:]

    months = []
    for i, t in enumerate(trajectory):
        m, o = t["m"], t["oni"]
        f, c = fits[m], clim[m]
        months.append({
            "y": t["y"], "m": m, "oni": o, **calendar[i],
            "pDry": pr["pdS"][i], "pDryNeutral": pr["pdN"][i],
            "pHot": pr["phS"][i], "pHotNeutral": pr["phN"][i],
            "dD3mm": float(f["zD3"].beta[1]) * o * c["D3"]["sd"],
            "dPpct": 100 * float(f["zP"].beta[1]) * o * c["P"]["sd"] / c["P"]["mean"],
            "dTmax": float(f["zT"].beta[1]) * o * c["Tmax"]["sd"],
            "slopeD": float(f["zD3"].beta[1]), "pSlopeD": pD[m], "qSlopeD": qD[m],
            "slopeT": float(f["zT"].beta[1]), "pSlopeT": pT[m], "qSlopeT": qT[m],
            "climP": c["P"]["mean"], "climTmax": c["Tmax"]["mean"],
            "r2D": f["zD3"].r2, "nYears": f["zD3"].n,
        })

    # Bootstrap por años completos (conserva la dependencia entre meses del mismo año).
    years = sorted({r["year"] for lst in rows for r in lst})
    rand = rng(seed)
    bS, bN, bD = [], [], []
    for _ in range(B):
        sample = [years[math.floor(rand() * len(years))] for _ in years]
        try:
            bf = []
            for d in md:
                idx = np.array([d.pos[y] for y in sample if y in d.pos], dtype=int)
                bf.append({"zD3": d.fit("zD3", idx), "zT": d.fit("zT", idx)})
            p = _month_probs(bf, trajectory)
            s, n = irc(calendar, p["pdS"], p["phS"]), irc(calendar, p["pdN"], p["phN"])
            bS.append(s); bN.append(n); bD.append(s - n)
        except np.linalg.LinAlgError:
            continue  # réplica degenerada
    p_boot = (sum(1 for d in bD if d <= 0) + 1) / (len(bD) + 1)

    return {
        "months": months,
        "irc": irc_s, "ircNeutral": irc_n,
        "delta": irc_s - irc_n, "ratio": irc_s / irc_n,
        "ci": [quantile(bS, 0.05), quantile(bS, 0.95)],
        "ciDelta": [quantile(bD, 0.05), quantile(bD, 0.95)],
        "pBoot": p_boot, "nBoot": len(bD), "significant": p_boot < 0.05,
        "category": category(irc_s), "categoryNeutral": category(irc_n),
        "nSigMonthsD": sum(1 for x in qD if x < 0.05),
        "nSigMonthsT": sum(1 for x in qT if x < 0.05),
        "yearsRange": [years[0], years[-1]],
    }


def analogs(dataset: dict, events: Sequence[dict], trajectory: Sequence[dict],
            calendar: Sequence[dict], year0: int) -> list[dict]:
    """Índice calculado con lo que realmente ocurrió en el punto durante Niños históricos,
    en la misma ventana relativa de meses que la proyección."""
    by_my = [{r["year"]: r for r in lst} for lst in dataset["rows"]]
    out = []
    for e in events:
        pd, ph, zd, zt = [], [], [], []
        ok = True
        for t in trajectory:
            r = by_my[t["m"]].get(t["y"] - year0 + e["year0"])
            if r is None:
                ok = False
                break
            zd.append(r["zD3"]); zt.append(r["zT"])
            pd.append(1 if r["zD3"] < -Z20 else 0)
            ph.append(1 if r["zT"] > Z20 else 0)
        if not ok:
            out.append({**e, "available": False})
            continue
        out.append({
            **e, "available": True,
            "ircObserved": irc(calendar, pd, ph),
            "meanZD3": sum(zd) / len(zd), "meanZT": sum(zt) / len(zt),
            "dryMonths": sum(pd), "hotMonths": sum(ph),
        })
    return out
