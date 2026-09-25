import datetime as dt
import json
import math
from pathlib import Path

import pytest

from superninio.datos.oni import cargar_oni
from superninio.modelo.climate import oni_at
from superninio.modelo.stats import randn, rng

FIXTURES = Path(__file__).parent / "fixtures"
HOY = dt.date(2026, 9, 25)


def clima_sintetico(eff_p: float, eff_t: float, seed: int, hasta: int = 2025) -> dict:
    """Clima mensual con efecto ENOS controlado (eff en desviaciones por unidad de ONI)."""
    oni, _ = cargar_oni()
    g = rng(seed)
    monthly = []
    for y in range(1950, hasta + 1):
        for m in range(12):
            o = oni_at(oni, y, m) or 0.0
            clim = 150 + 80 * math.sin(2 * math.pi * m / 6)
            monthly.append({"y": y, "m": m, "P": max(0.0, clim + 45 * (eff_p * o + randn(g))),
                            "ET0": 110 + 5 * randn(g), "Tmax": 24 + 0.8 * (eff_t * o + randn(g)) + 0.02 * (y - 1950)})
    return {"model": "era5_land", "end": f"{hasta}-12-31", "monthly": monthly}


@pytest.fixture(scope="session")
def referencia_js():
    return json.loads((FIXTURES / "referencia_js.json").read_text())


@pytest.fixture(scope="session")
def oni():
    return cargar_oni()[0]
