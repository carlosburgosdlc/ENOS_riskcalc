"""Explicación en lenguaje sencillo del resultado del IRCC (determinista: sin LLM, sin inventar cifras)."""
from __future__ import annotations

from ..modelo.phenology import MONTHS, MONTHS_LONG


def num(v: float, d: int = 0) -> str:
    """Número con formato colombiano: coma decimal."""
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fecha_larga(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} de {MONTHS_LONG[int(m) - 1]} de {y}"


def mes_largo(mes_id: str) -> str:
    y, m = mes_id.split("-")
    return f"{MONTHS_LONG[int(m) - 1]} de {y}"


def mes_corto(mes_id: str) -> str:
    y, m = mes_id.split("-")
    return f"{MONTHS[int(m) - 1]} {y[2:]}"


def _lista(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def nivel(p: float) -> str:
    """Probabilidad de mes seco/caliente -> nivel legible (la referencia climatológica es 20 %)."""
    if p >= 0.45:
        return "Alto"
    if p >= 0.25:
        return "Medio"
    return "Bajo"


def _texto_edad(meses: int) -> str:
    a, m = divmod(meses, 12)
    partes = []
    if a:
        partes.append(f"{a} año{'s' if a != 1 else ''}")
    if m:
        partes.append(f"{m} mes{'es' if m != 1 else ''}")
    return " y ".join(partes) or "menos de un mes"


def describir_cultivo(r: dict) -> str:
    e = r["entrada"]
    t = f"Cafetal de {_texto_edad(e['edad_meses'])}"
    if e["soqueado"]:
        t += f", soqueado hace {_texto_edad(e.get('meses_desde_zoca') or 0)}"
    return t


def diagnostico(r: dict) -> dict:
    """Devuelve {'titular', 'razones': [...], 'confianza', 'mensaje_whatsapp'} a partir de calcular_riesgo()."""
    ind, meses, e = r["indice"], r["meses"], r["entrada"]
    por_id = {m["mes"]: m for m in meses}
    razones: list[str] = []

    # 1. Cuánto cambia frente a un año normal
    ratio = ind["riesgo_relativo"] or 1
    if ratio >= 1.15:
        titular = (f"Con un Superniño, el riesgo de su cafetal sube de {num(ind['valor_anio_neutro'])} a "
                   f"{num(ind['valor'])} puntos sobre 100: {num(ratio, 1)} veces el riesgo de un año normal.")
    else:
        titular = (f"Su cafetal obtiene {num(ind['valor'])} puntos sobre 100. Un Superniño cambia poco el riesgo "
                   f"de su finca frente a un año normal ({num(ind['valor_anio_neutro'])} puntos).")

    # 2. Señal de lluvia
    secos = sorted((m for m in meses if m["senal_sequia_significativa"] and m["cambio_lluvia_pct"] < -5),
                   key=lambda m: m["cambio_lluvia_pct"])[:3]
    if secos:
        detalle = _lista([f"{num(-m['cambio_lluvia_pct'])} % menos en {MONTHS_LONG[int(m['mes'][5:]) - 1]}" for m in secos])
        razones.append(f"Menos lluvia: en los Niños del pasado, su finca recibió menos agua de lo normal. Para este escenario se espera {detalle}.")
    else:
        razones.append("Lluvia: el historial de su finca no muestra que El Niño reduzca la lluvia de forma clara.")

    # 3. Señal de calor
    calidos = [m for m in meses if m["senal_calor_significativa"] and m["cambio_tmax_c"] > 0.2]
    if calidos:
        mx = max(calidos, key=lambda m: m["cambio_tmax_c"])
        razones.append(f"Más calor: la temperatura máxima subiría hasta {num(mx['cambio_tmax_c'], 1)} °C por encima de lo normal "
                       f"(el mayor aumento sería en {MONTHS_LONG[int(mx['mes'][5:]) - 1]}).")

    # 4. Coincidencia con etapas sensibles
    crit = [por_id[i] for i in r["meses_criticos"] if i in por_id]
    if crit:
        detalle = _lista([f"{mes_corto(m['mes'])} ({m['etapa'].lower()})" for m in crit])
        razones.append(f"Momento del cultivo: los meses más delicados son {detalle}. Ahí coincide el tiempo seco o caliente con etapas en las que el café es más sensible.")

    # 5. Edad / zoca
    etapa = r["cultivo"]["etapa_actual"]
    if e["soqueado"] and (e.get("meses_desde_zoca") or 0) < 18:
        razones.append("Zoca: la raíz ya está establecida, lo que da algo de tolerancia a la sequía, pero los chupones jóvenes necesitan agua para crecer.")
    elif not e["soqueado"] and e["edad_meses"] < 18:
        razones.append("Cafetal joven: sus raíces todavía son cortas y depende mucho de la lluvia; una sequía puede causar pérdida de plantas.")
    elif (not e["soqueado"] and e["edad_meses"] > 84) or (e["soqueado"] and (e.get("meses_desde_zoca") or 0) > 60):
        razones.append("Cafetal envejecido: tiene menos vigor para aguantar el estrés, por eso su sensibilidad es un poco mayor.")
    else:
        razones.append(f"Cafetal en producción (hoy en {etapa.lower()}): la sequía afecta sobre todo la floración y el llenado del grano.")

    # 6. Altitud
    elev = r["ubicacion"].get("elevacion_m")
    if elev is not None and elev < 1300:
        razones.append(f"Altitud: a {num(elev)} m el café está más cerca de su límite de temperatura, por eso el calor pesa más en su nota.")
    elif elev is not None and elev > 1700:
        razones.append(f"Altitud: a {num(elev)} m la finca es más fresca, lo que le protege parcialmente del calor.")

    # 7. Historia real
    sup = [h for h in r["eventos_historicos"] if h["pico_oni"] >= 2.0]
    if sup:
        peor = max(sup, key=lambda h: h["indice_observado"])
        razones.append(f"Lo que ya pasó: en el Superniño de {peor['evento']} su finca tuvo {peor['meses_secos']} meses secos y "
                       f"{peor['meses_calientes']} meses calientes en el mismo periodo del año (índice observado: {num(peor['indice_observado'])}).")

    # 8. Confianza estadística
    if ind["significativo"]:
        p = "menor a 0,001" if ind["p_valor"] < 0.001 else num(ind["p_valor"], 3)
        confianza = (f"Este aumento de riesgo es estadísticamente confiable (p = {p}): se repite de forma consistente en "
                     f"{r['ubicacion']['anios_analizados'][1] - r['ubicacion']['anios_analizados'][0] + 1} años de datos de su finca, no es casualidad.")
    else:
        confianza = ("Ojo: en su finca la señal de El Niño no es estadísticamente clara. El resultado es orientativo: "
                     "el riesgo real puede parecerse al de un año normal.")

    crit_txt = ", ".join(mes_corto(i) for i in r["meses_criticos"])
    mensaje = (f"☕ *Diagnóstico Superniño*\n"
               f"Riesgo de su cafetal: *{num(ind['valor'])}/100 ({ind['categoria']})*\n"
               f"En un año normal: {num(ind['valor_anio_neutro'])}/100\n"
               f"Meses críticos: {crit_txt}\n\n"
               f"En el PDF le explico por qué y qué hacer. 👇")
    return {"titular": titular, "razones": razones, "confianza": confianza, "mensaje_whatsapp": mensaje}
