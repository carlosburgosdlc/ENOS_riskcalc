"""Punto de entrada único del motor de cálculo: entra un dict (JSON), sale un dict (JSON).

    from superninio import calcular_riesgo
    resultado = calcular_riesgo({"lat": 4.98, "lon": -75.6, "edad_meses": 48,
                                 "soqueado": False, "escenario": "super"})

Línea de comandos:
    python -m superninio.calculo entrada.json      (o)      echo '{...}' | python -m superninio.calculo
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from typing import Callable

from .datos.clima import obtener_clima, obtener_elevacion
from .datos.oni import cargar_oni
from .modelo.climate import build_dataset
from .modelo.phenology import (HARVEST_PATTERNS, MONTHS, crop_diagnosis, pattern_from_latitude,
                               sensitivity_calendar)
from .modelo.recommendations import meses_criticos, recommendations
from .modelo.risk import analogs, compute_risk
from .modelo.scenario import SCENARIOS, oni_template, scenario_trajectory

VERSION_MODELO = "2.0.0"

# JSON Schema de la entrada (sirve también como definición de tool para un agente).
ESQUEMA_ENTRADA = {
    "type": "object",
    "required": ["lat", "lon", "edad_meses", "soqueado", "escenario"],
    "properties": {
        "lat": {"type": "number", "minimum": -4.5, "maximum": 13.5, "description": "Latitud de la finca (Colombia)"},
        "lon": {"type": "number", "minimum": -82, "maximum": -66, "description": "Longitud de la finca (Colombia)"},
        "edad_meses": {"type": "integer", "minimum": 0, "maximum": 480, "description": "Edad del cafetal desde la siembra, en meses"},
        "soqueado": {"type": "boolean", "description": "¿El lote fue soqueado (zoca)?"},
        "meses_desde_zoca": {"type": "integer", "minimum": 0, "maximum": 240, "description": "Obligatorio si soqueado = true"},
        "escenario": {"type": "string", "enum": list(SCENARIOS), "description": "Intensidad de El Niño"},
        "pico_oni": {"type": "number", "minimum": 0.5, "maximum": 3.5, "description": "Opcional: pico ONI personalizado"},
        "patron_cosecha": {"type": "string", "enum": ["auto", *HARVEST_PATTERNS], "description": "Opcional. auto = según latitud"},
        "anio_evento": {"type": "integer", "description": "Opcional: año de desarrollo del evento El Niño"},
        "mes_inicio": {"type": "string", "pattern": r"^\d{4}-\d{2}$", "description": "Opcional: primer mes proyectado AAAA-MM"},
    },
}


class EntradaInvalida(ValueError):
    """La entrada no cumple ESQUEMA_ENTRADA."""


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validar(e: dict) -> None:
    if not isinstance(e, dict):
        raise EntradaInvalida("La entrada debe ser un objeto JSON")
    err = []
    if not _num(e.get("lat")) or not -4.5 <= e["lat"] <= 13.5:
        err.append("lat inválida (Colombia: -4.5 a 13.5)")
    if not _num(e.get("lon")) or not -82 <= e["lon"] <= -66:
        err.append("lon inválida (Colombia: -82 a -66)")
    if not _int(e.get("edad_meses")) or e["edad_meses"] < 0:
        err.append("edad_meses debe ser un entero >= 0")
    if not isinstance(e.get("soqueado"), bool):
        err.append("soqueado debe ser true o false")
    if e.get("soqueado") is True and (not _int(e.get("meses_desde_zoca")) or e["meses_desde_zoca"] < 0):
        err.append("meses_desde_zoca es obligatorio (entero >= 0) cuando soqueado = true")
    if e.get("escenario") not in SCENARIOS:
        err.append(f"escenario debe ser: {', '.join(SCENARIOS)}")
    if e.get("pico_oni") is not None and (not _num(e["pico_oni"]) or not 0.5 <= e["pico_oni"] <= 3.5):
        err.append("pico_oni debe estar entre 0.5 y 3.5")
    pc = e.get("patron_cosecha")
    if pc is not None and pc != "auto" and pc not in HARVEST_PATTERNS:
        err.append("patron_cosecha inválido")
    if e.get("mes_inicio") is not None and not re.fullmatch(r"\d{4}-\d{2}", str(e["mes_inicio"])):
        err.append("mes_inicio debe tener formato AAAA-MM")
    if err:
        raise EntradaInvalida("Entrada inválida: " + "; ".join(err))


def _r(v, d: int = 3):
    return None if v is None else round(float(v), d)


def calcular_riesgo(
    entrada: dict,
    *,
    obtener_clima_fn: Callable[[float, float], dict] = obtener_clima,
    obtener_elevacion_fn: Callable[[float, float], float | None] = obtener_elevacion,
    replicas: int = 1000,
    hoy: dt.date | None = None,
) -> dict:
    """Calcula el IRCC. El único I/O es la descarga de clima y altitud (inyectables)."""
    validar(entrada)
    hoy = hoy or dt.date.today()
    lat, lon = float(entrada["lat"]), float(entrada["lon"])
    oni, oni_meta = cargar_oni()

    # 1. Datos externos
    clima = obtener_clima_fn(lat, lon)
    elevacion = obtener_elevacion_fn(lat, lon)

    # 2. Cultivo
    pc = entrada.get("patron_cosecha")
    patron = pattern_from_latitude(lat) if pc in (None, "auto") else pc
    cultivo = {
        "ageMonths": entrada["edad_meses"], "zoca": entrada["soqueado"],
        "monthsSinceZoca": entrada.get("meses_desde_zoca") or 0 if entrada["soqueado"] else 0,
        "pattern": patron, "elevation": elevacion,
    }

    # 3. Escenario: ONI de los próximos 12 meses
    pico = entrada.get("pico_oni") or SCENARIOS[entrada["escenario"]]["peak"]
    if entrada.get("mes_inicio"):
        iy, im = (int(x) for x in entrada["mes_inicio"].split("-"))
        im -= 1
    else:
        iy, im = divmod(hoy.year * 12 + hoy.month, 12)  # mes siguiente
    anio_evento = entrada.get("anio_evento") or (hoy.year if hoy.month >= 3 else hoy.year - 1)
    plantilla = oni_template(oni, 1.5)
    trayectoria = scenario_trajectory(plantilla, pico, anio_evento, iy, im)

    # 4. Modelo
    dataset = build_dataset(clima["monthly"], oni)
    calendario = sensitivity_calendar(cultivo, trayectoria)
    res = compute_risk(dataset, trayectoria, calendario, B=replicas)
    hist = analogs(dataset, plantilla["events"], trayectoria, calendario, anio_evento)
    etapa_hoy = sensitivity_calendar(
        {**cultivo, "ageMonths": cultivo["ageMonths"] - 1, "monthsSinceZoca": cultivo["monthsSinceZoca"] - 1},
        [{"y": hoy.year, "m": hoy.month - 1}],
    )[0]["stage"]

    # 5. Salida
    advertencias = crop_diagnosis(cultivo)  # para el caficultor
    advertencias_tecnicas = []  # para el equipo, no se muestran al caficultor
    if oni_meta.get("provisional"):
        advertencias_tecnicas.append("Serie ONI provisional: ejecutar scripts/update_oni.py antes de usar en producción.")
    if clima.get("model") != "era5_land":
        advertencias_tecnicas.append("ERA5-Land no disponible; se usó ERA5 (menor resolución).")
    if not res["significant"]:
        advertencias.append("La señal de El Niño no es estadísticamente significativa en esta ubicación: el aumento de riesgo no se distingue de la variabilidad natural.")

    def mes_id(m):
        return f"{m['y']}-{m['m'] + 1:02d}"

    return {
        "version_modelo": VERSION_MODELO,
        "fecha_calculo": hoy.isoformat(),
        "entrada": {**entrada, "patron_cosecha": patron, "pico_oni": pico, "anio_evento": anio_evento},
        "ubicacion": {"lat": lat, "lon": lon, "elevacion_m": elevacion, "fuente_clima": clima.get("model"),
                      "datos_hasta": clima.get("end"), "anios_analizados": res["yearsRange"]},
        "cultivo": {"etapa_actual": etapa_hoy, "patron_cosecha": HARVEST_PATTERNS[patron]["label"]},
        "indice": {
            "valor": _r(res["irc"], 1), "categoria": res["category"]["label"],
            "ic90": [_r(res["ci"][0], 1), _r(res["ci"][1], 1)],
            "valor_anio_neutro": _r(res["ircNeutral"], 1), "categoria_anio_neutro": res["categoryNeutral"]["label"],
            "aumento": _r(res["delta"], 1), "aumento_ic90": [_r(res["ciDelta"][0], 1), _r(res["ciDelta"][1], 1)],
            "riesgo_relativo": _r(res["ratio"], 2), "p_valor": _r(res["pBoot"], 4),
            "significativo": res["significant"], "replicas_bootstrap": res["nBoot"],
            "meses_senal_sequia": res["nSigMonthsD"], "meses_senal_calor": res["nSigMonthsT"],
            "interpretacion": "Probabilidad media (0-100) de mes seco o caliente, ponderada por la sensibilidad de la etapa del cultivo. Clima normal: cerca de 20.",
        },
        "meses": [{
            "mes": mes_id(m), "etiqueta": f"{MONTHS[m['m']]} {m['y']}", "oni": _r(m["oni"], 2),
            "etapa": m["stage"], "sensibilidad_sequia": _r(m["Sd"], 2), "sensibilidad_calor": _r(m["Sh"], 2),
            "prob_mes_seco": _r(m["pDry"]), "prob_mes_seco_neutro": _r(m["pDryNeutral"]),
            "prob_mes_caliente": _r(m["pHot"]), "prob_mes_caliente_neutro": _r(m["pHotNeutral"]),
            "cambio_lluvia_pct": _r(m["dPpct"], 1), "cambio_tmax_c": _r(m["dTmax"], 2),
            "senal_sequia_significativa": m["qSlopeD"] < 0.05, "senal_calor_significativa": m["qSlopeT"] < 0.05,
        } for m in res["months"]],
        "meses_criticos": [mes_id(m) for m in meses_criticos(res)],
        "eventos_historicos": [{
            "evento": f"{a['year0']}-{a['year0'] + 1}", "pico_oni": a["peak"], "clase": a["class"],
            "indice_observado": _r(a["ircObserved"], 1), "meses_secos": a["dryMonths"], "meses_calientes": a["hotMonths"],
        } for a in hist if a["available"]],
        "recomendaciones": recommendations(res, cultivo),
        "advertencias": advertencias,
        "advertencias_tecnicas": advertencias_tecnicas,
    }


def main() -> None:
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        print(json.dumps(calcular_riesgo(json.loads(raw)), ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001 - la CLI reporta cualquier error como JSON
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
