"""Utilidades estadísticas: OLS, t de Student, Benjamini-Hochberg, cuantiles y PRNG reproducible."""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

_MASK = 0xFFFFFFFF


def mean(a: Sequence[float]) -> float:
    return float(np.mean(a))


def sd(a: Sequence[float]) -> float:
    return float(np.std(a, ddof=1))


def quantile(a: Sequence[float], q: float) -> float:
    """Cuantil con interpolación lineal (tipo 7, igual que R/numpy por defecto)."""
    s = sorted(a)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _i32(x: int) -> int:
    x &= _MASK
    return x - (1 << 32) if x & 0x80000000 else x


def _imul(a: int, b: int) -> int:
    return _i32((a & _MASK) * (b & _MASK))


def rng(seed: int = 12345) -> Callable[[], float]:
    """PRNG mulberry32 (idéntico bit a bit a la versión JS original) para bootstrap reproducible."""
    t = seed & _MASK

    def rand() -> float:
        nonlocal t
        t = (t + 0x6D2B79F5) & _MASK
        r = _imul(t ^ (t >> 15), 1 | t)
        r = _i32(r + _imul(r ^ ((r & _MASK) >> 7), 61 | r)) ^ r
        return ((r ^ ((r & _MASK) >> 14)) & _MASK) / 4294967296

    return rand


def randn(rand: Callable[[], float]) -> float:
    """Normal estándar por Box-Muller (solo para simulaciones en tests)."""
    u = 1 - rand()
    v = rand()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def _log_gamma(x: float) -> float:
    c = (76.18009172947146, -86.50532032941677, 24.01409824083091,
         -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5)
    y = x
    tmp = x + 5.5 - (x + 0.5) * math.log(x + 5.5)
    ser = 1.000000000190015
    for ci in c:
        y += 1
        ser += ci / y
    return -tmp + math.log((2.5066282746310005 * ser) / x)


def _betacf(a: float, b: float, x: float) -> float:
    maxit, eps, fpmin = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - (qab * x) / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = (m * (b - m) * x) / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1 / d
        h *= d * c
        aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1 / d
        dl = d * c
        h *= dl
        if abs(dl - 1) < eps:
            break
    return h


def beta_inc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(_log_gamma(a + b) - _log_gamma(a) - _log_gamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t: float, df: float) -> float:
    """P(|T| > |t|) para una t de Student con df grados de libertad."""
    return beta_inc(df / 2, 0.5, df / (df + t * t))


def t_cdf(t: float, df: float) -> float:
    p = 0.5 * beta_inc(df / 2, 0.5, df / (df + t * t))
    return 1 - p if t >= 0 else p


class OLS:
    """Resultado de mínimos cuadrados ordinarios."""

    __slots__ = ("beta", "se", "t", "p", "resid", "df", "sigma", "xtx_inv", "r2", "n")

    def __init__(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        n, p = X.shape
        xtx_inv = np.linalg.inv(X.T @ X)
        beta = xtx_inv @ (X.T @ y)
        resid = y - X @ beta
        df = n - p
        sigma2 = float(resid @ resid) / df
        se = np.sqrt(sigma2 * np.diag(xtx_inv))
        t = beta / se
        ss_tot = float(((y - y.mean()) ** 2).sum())
        self.beta, self.se, self.t = beta, se, t
        self.p = np.array([t_two_sided_p(float(tj), df) for tj in t])
        self.resid, self.df, self.sigma = resid, df, math.sqrt(sigma2)
        self.xtx_inv, self.n = xtx_inv, n
        self.r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0


def ols(X, y) -> OLS:
    return OLS(X, y)


def leverage(xtx_inv: np.ndarray, x0: Sequence[float]) -> float:
    """Palanca de un punto nuevo: x0' (X'X)^-1 x0."""
    x = np.asarray(x0, dtype=float)
    return float(x @ xtx_inv @ x)


def benjamini_hochberg(pvals: Sequence[float]) -> list[float]:
    """Valores q de Benjamini-Hochberg en el orden original."""
    m = len(pvals)
    idx = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    prev = 1.0
    for k in range(m - 1, -1, -1):
        i = idx[k]
        prev = min(prev, pvals[i] * m / (k + 1))
        q[i] = prev
    return q
