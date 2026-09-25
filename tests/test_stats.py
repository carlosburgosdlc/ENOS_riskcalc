import numpy as np
import pytest

from superninio.modelo.stats import benjamini_hochberg, ols, quantile, randn, rng, t_cdf, t_two_sided_p


def test_p_valor_t_student():
    assert t_two_sided_p(2.0, 10) == pytest.approx(0.07339, abs=1e-4)
    assert t_two_sided_p(1.96, 1e6) == pytest.approx(0.05, abs=1e-3)
    assert t_cdf(-2.228, 10) == pytest.approx(0.025, abs=1e-3)


def test_ols_recupera_coeficientes():
    r = rng(1)
    X, y = [], []
    for _ in range(500):
        a, b = randn(r), randn(r)
        X.append([1, a, b])
        y.append(1 + 2 * a - 0.5 * b + 0.1 * randn(r))
    f = ols(np.array(X), np.array(y))
    assert f.beta == pytest.approx([1, 2, -0.5], abs=0.02)
    assert f.p[1] < 1e-10


def test_benjamini_hochberg():
    assert [round(v, 4) for v in benjamini_hochberg([0.01, 0.04, 0.03, 0.5])] == [0.04, 0.0533, 0.0533, 0.5]


def test_cuantil():
    assert quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert quantile([1, 2, 3, 4], 0.25) == 1.75


def test_rng_identico_a_js(referencia_js):
    g = rng(20260922)
    assert [g() for _ in range(8)] == referencia_js["rng_20260922"]
    g2 = rng(1)
    assert [randn(g2) for _ in range(4)] == pytest.approx(referencia_js["randn_1"], abs=1e-12)


def test_t_identico_a_js(referencia_js):
    for t, df, p in referencia_js["t_p"]:
        assert t_two_sided_p(t, df) == pytest.approx(p, rel=1e-9)
