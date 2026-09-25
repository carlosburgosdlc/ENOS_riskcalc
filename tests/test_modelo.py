from superninio.modelo.climate import build_dataset, daily_to_monthly
from superninio.modelo.phenology import sensitivity_calendar
from superninio.modelo.risk import OLS, _design, analogs, compute_risk, exceed_prob
from superninio.modelo.scenario import find_el_nino_events, oni_template, scenario_trajectory

from .conftest import clima_sintetico

CROP = {"ageMonths": 48, "zoca": False, "monthsSinceZoca": 0, "pattern": "centro", "elevation": 1500}


def _fit(rows, v):
    import numpy as np
    return OLS(np.array([_design(r["oni"], r["year"]) for r in rows]), np.array([r[v] for r in rows]))


def test_daily_to_monthly():
    time, p, e, t = [], [], [], []
    for d in range(1, 32):
        time.append(f"2000-01-{d:02d}"); p.append(2); e.append(3); t.append(20 + d % 2)
    for d in range(1, 11):
        time.append(f"2000-02-{d:02d}"); p.append(1); e.append(1); t.append(20)
    mo = daily_to_monthly({"time": time, "precipitation_sum": p, "et0_fao_evapotranspiration": e, "temperature_2m_max": t})
    assert mo[0]["P"] == 62 and mo[0]["ET0"] == 93
    assert abs(mo[0]["Tmax"] - 20.516) < 0.01
    assert mo[1]["P"] is None


def test_error_tipo_I_calibrado(oni):
    """Sin señal ENOS, la pendiente sale significativa ~5 % de las veces."""
    n, rej = 300, 0
    for s in range(n):
        ds = build_dataset(clima_sintetico(0, 0, s + 1)["monthly"], oni)
        rej += _fit(ds["rows"][0], "zD3").p[1] < 0.05
    assert 0.02 < rej / n < 0.09


def test_senal_seca_aumenta_probabilidad(oni):
    ds = build_dataset(clima_sintetico(-0.6, 0.6, 7)["monthly"], oni)
    f = _fit(ds["rows"][0], "zD3")
    assert f.beta[1] < -0.2 and f.p[1] < 0.01
    pn, ps = exceed_prob(f, [1, 0, 2.6], -1), exceed_prob(f, [1, 2.4, 2.6], -1)
    # El 20 % climatológico incluye años Niño y Niña: un año neutro queda por debajo.
    assert 0.02 < pn < 0.25
    assert ps > 0.4 and ps > 3 * pn


def test_eventos_y_plantilla(oni):
    ev = find_el_nino_events(oni)
    assert next(e for e in ev if e["year0"] == 1997)["peak"] >= 2.3
    assert next(e for e in ev if e["year0"] == 2015)["peak"] >= 2.5
    tpl = oni_template(oni, 1.5)
    assert len(tpl["events"]) >= 8
    assert 20 <= tpl["shape"].index(1.0) <= 24
    tr = scenario_trajectory(tpl, 2.4, 2026, 2026, 9)
    assert len(tr) == 12 and max(x["oni"] for x in tr) > 2.2 and tr[11]["oni"] < 1.0


def test_riesgo_significativo_con_senal_y_no_con_ruido(oni):
    tpl = oni_template(oni, 1.5)
    tr = scenario_trajectory(tpl, 2.4, 2026, 2026, 9)
    cal = sensitivity_calendar(CROP, tr)
    sig = compute_risk(build_dataset(clima_sintetico(-0.6, 0.6, 11)["monthly"], oni), tr, cal, B=200)
    assert sig["irc"] > sig["ircNeutral"] + 10 and sig["significant"]
    assert sig["ci"][0] < sig["irc"] < sig["ci"][1]
    nul = compute_risk(build_dataset(clima_sintetico(0, 0, 14)["monthly"], oni), tr, cal, B=200)
    assert abs(nul["delta"]) < 6


def test_analogos(oni):
    ds = build_dataset(clima_sintetico(-0.6, 0.6, 11)["monthly"], oni)
    tpl = oni_template(oni, 1.5)
    tr = scenario_trajectory(tpl, 2.4, 2026, 2026, 9)
    an = analogs(ds, tpl["events"], tr, sensitivity_calendar(CROP, tr), 2026)
    a97 = next(a for a in an if a["year0"] == 1997)
    assert a97["available"] and a97["meanZD3"] < 0
