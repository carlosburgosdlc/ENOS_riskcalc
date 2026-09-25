"""Recomendaciones de manejo según los meses de mayor riesgo y la etapa del cultivo.

Basadas en recomendaciones técnicas generales de Cenicafé / FNC; no reemplazan la visita técnica.
Devuelve una lista de {"tema", "titulo", "texto"} en texto plano.
"""
from __future__ import annotations

import re
from typing import Sequence

from .phenology import MONTHS


def _label(m: dict) -> str:
    return f"{MONTHS[m['m']]} {str(m['y'])[2:]}"


def _list(ms: Sequence[dict]) -> str:
    if len(ms) > 4:
        return f"{len(ms)} meses entre {_label(ms[0])} y {_label(ms[-1])}"
    return ", ".join(_label(m) for m in ms)


def _risky(m: dict) -> float:
    return m["Sd"] * m["pDry"] + m["Sh"] * m["pHot"]


def meses_criticos(res: dict, n: int = 3) -> list[dict]:
    top = sorted(res["months"], key=_risky, reverse=True)[:n]
    return sorted(top, key=lambda m: m["y"] * 12 + m["m"])


def recommendations(res: dict, crop: dict) -> list[dict]:
    months = res["months"]
    dry = [m for m in months if m["pDry"] >= 0.35 and m["pDry"] > m["pDryNeutral"] + 0.08]
    hot = [m for m in months if m["pHot"] >= 0.35 and m["pHot"] > m["pHotNeutral"] + 0.08]

    def has(ms, pattern):
        return [m for m in ms if re.search(pattern, m["stage"])]

    out = [{"tema": "criticos", "titulo": "Meses críticos para su lote",
            "texto": f"{_list(meses_criticos(res))}: es donde más se juntan la probabilidad de estrés y la sensibilidad de la etapa del café."}]

    if not res["significant"]:
        out.append({"tema": "general", "titulo": "Señal débil en su zona",
                     "texto": "Como la señal de El Niño no es clara en su finca, priorice las buenas prácticas generales y siga los boletines del IDEAM y de la FNC antes de hacer inversiones grandes pensando solo en El Niño."})
    est = has(dry, r"Establecimiento|Levante")
    if est:
        out.append({"tema": "joven", "titulo": f"Cafetal joven con riesgo de sequía ({_list(est)})",
                    "texto": "Ponga cobertura muerta (residuos de arvenses, pulpa compostada) en el plato, establezca sombrío transitorio y prevea riego de auxilio. Si aún no ha sembrado, evite trasplantar en esos meses."})
    zo = has(dry, r"zoca|chupones")
    if zo:
        out.append({"tema": "zoca", "titulo": f"Zoca en meses secos ({_list(zo)})",
                    "texto": "La raíz ya establecida le da algo de tolerancia, pero conserve la cobertura del suelo y seleccione los chupones cuando haya humedad suficiente."})
    if not crop["zoca"] and crop["ageMonths"] > 84:
        out.append({"tema": "renovacion", "titulo": "Planee bien la renovación",
                    "texto": "Si va a zoquear, no lo haga justo antes de los meses de mayor riesgo: los chupones jóvenes y la pérdida de follaje dejan al lote más expuesto."})
    flo = has(dry, r"Floración|Diferenciación")
    if flo:
        out.append({"tema": "floracion", "titulo": f"Floración con sequía ({_list(flo)})",
                    "texto": "Hay riesgo de floraciones dispersas y flores estrella (abortadas). Conserve la humedad del suelo con manejo integrado de arvenses: deje arvenses nobles de porte bajo en las calles y limpie solo el plato; evite desyerbar a ras o con herbicida en toda el área."})
    fr = has(dry, r"Expansión|Llenado")
    if fr:
        out.append({"tema": "fruto", "titulo": f"Fruto en desarrollo con déficit de agua ({_list(fr)})",
                    "texto": "Es la etapa donde la sequía más reduce el tamaño del grano y aumenta los granos vanos o negros. Fraccione la fertilización y aplíquela solo con el suelo húmedo: sin lluvia se pierde el nitrógeno y no se absorbe el potasio."})
    broca = [m for m in months if m["pHot"] >= 0.3 and re.search(r"Llenado|Maduración", m["stage"])]
    if broca:
        out.append({"tema": "broca", "titulo": f"Broca ({_list(broca)})",
                    "texto": "El calor acelera su ciclo. Haga muestreos mensuales de infestación (actúe si supera el 2 %), recolecte a tiempo y haga repase (re-re) de frutos maduros, sobremaduros y caídos."})
    elev = crop.get("elevation")
    if hot and elev is not None and elev < 1400:
        alt = f"{round(elev):,}".replace(",", ".")
        out.append({"tema": "sombrio", "titulo": f"Finca baja con meses calientes ({_list(hot)})",
                    "texto": f"A {alt} m el café está cerca de su límite de temperatura. El sombrío regulado baja la temperatura de las hojas; si no tiene, planéelo como adaptación a mediano plazo."})
    if len(dry) >= 4:
        out.append({"tema": "agua", "titulo": "Guarde agua",
                    "texto": "Con 4 o más meses de alta probabilidad de sequía, evalúe cosechar y almacenar agua (reservorios, tanques) para el beneficio y el riego de auxilio de almácigos o lotes jóvenes."})
    out.append({"tema": "seguimiento", "titulo": "Haga seguimiento",
                "texto": "Registre la lluvia de su finca con un pluviómetro para compararla con este diagnóstico y consulte a su extensionista del Comité de Cafeteros."})
    return out
