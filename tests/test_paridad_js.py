"""El port a Python reproduce exactamente la implementación JavaScript original (v1.0.0)."""
import pytest

from superninio.calculo import calcular_riesgo

from .conftest import HOY

NUMERICOS = ["oni", "sensibilidad_sequia", "sensibilidad_calor", "prob_mes_seco", "prob_mes_seco_neutro",
             "prob_mes_caliente", "prob_mes_caliente_neutro", "cambio_lluvia_pct", "cambio_tmax_c",
             "senal_sequia_significativa", "senal_calor_significativa", "mes"]


@pytest.mark.parametrize("i", [0, 1, 2])
def test_paridad(referencia_js, i):
    caso = referencia_js["casos"][i]
    out = calcular_riesgo(caso["entrada"], obtener_clima_fn=lambda *_: caso["clima"],
                          obtener_elevacion_fn=lambda *_: caso["elevacion"], replicas=referencia_js["replicas"], hoy=HOY)
    js = caso["salida"]
    for k, v in js["indice"].items():
        if k != "interpretacion":
            assert out["indice"][k] == v, k
    for a, b in zip(out["meses"], js["meses"], strict=True):
        for k in NUMERICOS:
            assert a[k] == b[k], (a["mes"], k)
    for a, b in zip(out["eventos_historicos"], js["eventos_historicos"], strict=True):
        for k in ("evento", "pico_oni", "indice_observado", "meses_secos", "meses_calientes"):
            assert a[k] == b[k]
    assert len(out["recomendaciones"]) == len(js["recomendaciones"])
