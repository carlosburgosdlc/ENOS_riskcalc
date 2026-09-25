import json

import pytest

from superninio.calculo import ESQUEMA_ENTRADA, EntradaInvalida, calcular_riesgo

from .conftest import HOY, clima_sintetico

CLIMA = clima_sintetico(-0.5, 0.5, 5)
OPC = dict(obtener_clima_fn=lambda *_: CLIMA, obtener_elevacion_fn=lambda *_: 1500, replicas=200, hoy=HOY)
BASE = {"lat": 4.98, "lon": -75.6, "edad_meses": 48, "soqueado": False, "escenario": "super"}


def test_contrato_json():
    out = calcular_riesgo(BASE, **OPC)
    assert len(out["meses"]) == 12 and out["meses"][0]["mes"] == "2026-10"
    assert out["indice"]["valor"] > out["indice"]["valor_anio_neutro"]
    assert isinstance(out["indice"]["significativo"], bool)
    assert out["entrada"]["patron_cosecha"] == "centro"
    assert all(set(r) == {"tema", "titulo", "texto"} for r in out["recomendaciones"])
    assert len(out["meses_criticos"]) == 3
    assert json.loads(json.dumps(out)) == out  # serializable


def test_determinista():
    assert calcular_riesgo(BASE, **OPC) == calcular_riesgo(BASE, **OPC)


@pytest.mark.parametrize("cambio, error", [
    ({"lat": 40}, "lat inválida"),
    ({"soqueado": True}, "meses_desde_zoca"),
    ({"escenario": "x"}, "escenario"),
    ({"edad_meses": -1}, "edad_meses"),
])
def test_validacion(cambio, error):
    with pytest.raises(EntradaInvalida, match=error):
        calcular_riesgo({**BASE, **cambio}, **OPC)


def test_esquema():
    assert ESQUEMA_ENTRADA["required"] == ["lat", "lon", "edad_meses", "soqueado", "escenario"]


def test_advertencias_tecnicas_separadas():
    out = calcular_riesgo(BASE, **OPC)
    assert not any("update_oni" in a for a in out["advertencias"])
