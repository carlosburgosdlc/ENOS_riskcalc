"""Descarga de clima histórico (ERA5-Land vía Open-Meteo) y altitud, con caché en disco opcional.

Variables de entorno:
  OPEN_METEO_API_KEY     clave del plan comercial de Open-Meteo (obligatoria para uso comercial).
  SUPERNINIO_CACHE_DIR   carpeta de caché del clima mensual por punto (recomendado en producción).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..modelo.climate import daily_to_monthly

START_DATE = "1950-01-01"
DAILY_VARS = "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
TIMEOUT_S = 90


class ErrorDatos(RuntimeError):
    """Fallo al obtener datos externos."""


def _base(host: str) -> tuple[str, dict]:
    key = os.environ.get("OPEN_METEO_API_KEY")
    if key:
        return f"https://customer-{host}", {"apikey": key}
    return f"https://{host}", {}


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": "superninio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            reason = json.loads(e.read().decode()).get("reason", "")
        except Exception:  # noqa: BLE001 - el cuerpo del error es opcional
            reason = ""
        raise ErrorDatos(f"HTTP {e.code} {reason}".strip()) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorDatos(f"Sin conexión con {url}: {e}") from e
    if data.get("error"):
        raise ErrorDatos(data.get("reason", "Error de Open-Meteo"))
    return data


def last_complete_month_end(today: dt.date | None = None) -> str:
    """Último día del mes más reciente con datos ERA5 publicados (retraso ~5 días)."""
    d = (today or dt.date.today()) - dt.timedelta(days=7)
    return (d.replace(day=1) - dt.timedelta(days=1)).isoformat()


def _cache_path(lat: float, lon: float, end: str) -> Path | None:
    folder = os.environ.get("SUPERNINIO_CACHE_DIR")
    if not folder:
        return None
    # ERA5-Land tiene celdas de 0.1°: redondear a 0.05° reutiliza la caché entre fincas vecinas.
    key = f"{round(lat * 20) / 20:.2f}_{round(lon * 20) / 20:.2f}_{end}.json"
    return Path(folder) / key


def obtener_clima(lat: float, lon: float) -> dict:
    """{'model', 'end', 'monthly': [{'y','m','P','ET0','Tmax'}]} desde 1950 para el punto."""
    end = last_complete_month_end()
    cache = _cache_path(lat, lon, end)
    if cache and cache.exists():
        return json.loads(cache.read_text())
    url, extra = _base("archive-api.open-meteo.com")
    params = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": START_DATE,
              "end_date": end, "daily": DAILY_VARS, "timezone": "America/Bogota", **extra}
    model = "era5_land"
    try:
        j = _get_json(f"{url}/v1/archive", {**params, "models": model})
    except ErrorDatos:
        model = "era5"
        j = _get_json(f"{url}/v1/archive", {**params, "models": model})
    out = {"model": model, "end": end, "monthly": daily_to_monthly(j["daily"])}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
    return out


def obtener_elevacion(lat: float, lon: float) -> float | None:
    """Altitud (m) del DEM Copernicus 90 m; None si el servicio falla."""
    url, extra = _base("api.open-meteo.com")
    try:
        j = _get_json(f"{url}/v1/elevation", {"latitude": lat, "longitude": lon, **extra})
        return (j.get("elevation") or [None])[0]
    except ErrorDatos:
        return None
