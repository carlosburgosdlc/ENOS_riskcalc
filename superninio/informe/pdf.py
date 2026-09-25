"""Reporte PDF del diagnóstico Superniño para enviar al caficultor por WhatsApp.

Pensado para leerse en el celular: letra grande, una idea por bloque, colores siempre acompañados
de texto (Bajo / Medio / Alto) para no depender solo del color.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from .diagnostico import describir_cultivo, diagnostico, fecha_larga, mes_corto, nivel, num

VERDE = colors.HexColor("#1f6b3a")
TINTA = colors.HexColor("#0b0b0b")
TINTA2 = colors.HexColor("#52514e")
LINEA = colors.HexColor("#e1e0d9")
FONDO = colors.HexColor("#f6f5f1")
CATEGORIA = {  # paleta de estado: bueno / advertencia / serio / crítico
    "Bajo": colors.HexColor("#0ca30c"), "Moderado": colors.HexColor("#fab219"),
    "Alto": colors.HexColor("#ec835a"), "Muy alto": colors.HexColor("#d03b3b"),
}
NIVEL_FONDO = {"Bajo": colors.HexColor("#e3f4e3"), "Medio": colors.HexColor("#fdf0cf"), "Alto": colors.HexColor("#f9d9d4")}

# Helvetica (WinAnsi) no tiene estos glifos: se reemplazan para evitar cuadros negros.
_REEMPLAZOS = {"≈": "aprox. ", "≥": ">=", "≤": "<=", "−": "-", "→": "->", "“": '"', "”": '"', "’": "'"}


def _t(s: str) -> str:
    for a, b in _REEMPLAZOS.items():
        s = s.replace(a, b)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join(ch for ch in s if ord(ch) < 0x2000 or ch in "–—•…€")


def _estilos() -> dict:
    base = dict(fontName="Helvetica", textColor=TINTA, leading=15, fontSize=11)
    return {
        "h1": ParagraphStyle("h1", **{**base, "fontName": "Helvetica-Bold", "fontSize": 15, "leading": 19, "textColor": VERDE, "spaceBefore": 10, "spaceAfter": 6}),
        "p": ParagraphStyle("p", **base, spaceAfter=4),
        "p2": ParagraphStyle("p2", **{**base, "textColor": TINTA2, "fontSize": 9.5, "leading": 13}),
        "small": ParagraphStyle("small", **{**base, "textColor": TINTA2, "fontSize": 8, "leading": 10.5}),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 9.5, "leading": 12}),
        "cellb": ParagraphStyle("cellb", **{**base, "fontName": "Helvetica-Bold", "fontSize": 9.5, "leading": 12}),
        "big": ParagraphStyle("big", **{**base, "fontName": "Helvetica-Bold", "fontSize": 44, "leading": 48, "alignment": TA_CENTER, "textColor": colors.white}),
        "bigsub": ParagraphStyle("bigsub", **{**base, "fontName": "Helvetica-Bold", "fontSize": 13, "leading": 16, "alignment": TA_CENTER, "textColor": colors.white}),
    }


def _pie(fecha: str, version: str):
    def dibujar(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(VERDE)
        c.rect(0, h - 26 * mm, w, 26 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(16 * mm, h - 14 * mm, "Diagnóstico Superniño")
        c.setFont("Helvetica", 10.5)
        c.drawString(16 * mm, h - 20.5 * mm, "Riesgo climático de su cafetal ante El Niño")
        c.drawRightString(w - 16 * mm, h - 14 * mm, fecha)
        c.setFillColor(TINTA2)
        c.setFont("Helvetica", 7.5)
        c.drawString(16 * mm, 9 * mm, f"Modelo IRCC v{version} · Herramienta de apoyo; no reemplaza la asistencia técnica ni los boletines del IDEAM.")
        c.drawRightString(w - 16 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()
    return dibujar


def generar_pdf(resultado: dict, finca: dict | None = None) -> bytes:
    """Genera el PDF a partir de calcular_riesgo().

    finca (opcional): {"nombre": str, "ubicacion": "Vereda X, Municipio, Depto", "precision": "gps"|"vereda"|"municipio"}.
    """
    finca = finca or {}
    r, ind, E = resultado, resultado["indice"], _estilos()
    d = diagnostico(r)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=32 * mm, bottomMargin=16 * mm,
                            title="Diagnóstico Superniño", author="AMY", subject="Riesgo climático del café ante El Niño")
    ancho = A4[0] - 32 * mm
    s: list = []

    # --- Su finca
    u = r["ubicacion"]
    lugar = finca.get("ubicacion") or f"Lat {num(u['lat'], 4)}, Lon {num(u['lon'], 4)}"
    if finca.get("precision") == "municipio":
        lugar += " (ubicación aproximada: centro del municipio)"
    filas = [
        ["Finca", finca.get("nombre") or "-"],
        ["Ubicación", lugar],
        ["Altitud", f"{num(u['elevacion_m'])} m s.n.m." if u.get("elevacion_m") is not None else "Sin dato"],
        ["Cultivo", f"{describir_cultivo(r)}. Etapa actual: {r['cultivo']['etapa_actual'].lower()}."],
        ["Cosecha", r["cultivo"]["patron_cosecha"]],
        ["Escenario", f"Superniño (pico ONI {num(r['entrada']['pico_oni'], 1)} °C) · {mes_corto(r['meses'][0]['mes'])} a {mes_corto(r['meses'][-1]['mes'])}"
         if r["entrada"]["escenario"] == "super" else f"El Niño {r['entrada']['escenario']} (pico ONI {num(r['entrada']['pico_oni'], 1)} °C)"],
    ]
    t = Table([[Paragraph(_t(a), E["cellb"]), Paragraph(_t(b), E["cell"])] for a, b in filas], colWidths=[28 * mm, ancho - 28 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FONDO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINEA), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    s += [Paragraph("Su finca", E["h1"]), t]

    # --- Resultado
    col = CATEGORIA[ind["categoria"]]
    caja = Table([[Paragraph(num(ind["valor"]), E["big"])], [Paragraph("de 100", E["bigsub"])],
                  [Paragraph(_t(f"Riesgo {ind['categoria']}"), E["bigsub"])]], colWidths=[55 * mm])
    caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
    lado = [
        Paragraph(_t(d["titular"]), E["p"]), Spacer(1, 4),
        Paragraph(_t(f"<b>Año normal:</b> {num(ind['valor_anio_neutro'])} ({ind['categoria_anio_neutro']}) · "
                     f"<b>Rango probable:</b> {num(ind['ic90'][0])} a {num(ind['ic90'][1])}").replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"), E["p2"]),
        Spacer(1, 4),
        Paragraph(_t("Escala: 0-25 bajo · 25-35 moderado · 35-50 alto · 50-100 muy alto. Un año normal suele dar cerca de 20."), E["small"]),
    ]
    res = Table([[caja, lado]], colWidths=[60 * mm, ancho - 60 * mm])
    res.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 0), (1, 0), 10)]))
    s += [Paragraph("Resultado", E["h1"]), res]

    # --- ¿Por qué?
    items = [ListItem(Paragraph(_t(x), E["p"]), leftIndent=12, value="•") for x in d["razones"]]
    s += [Paragraph("¿Por qué obtuvo esta nota?", E["h1"]), ListFlowable(items, bulletType="bullet", start="•", leftIndent=12),
          Spacer(1, 4), Paragraph(_t(d["confianza"]), E["p2"])]

    # --- Mes a mes
    cab = ["Mes", "Etapa del café", "Sequía", "Calor", "Lluvia vs. normal"]
    datos = [[Paragraph(f"<b>{c}</b>", E["cell"]) for c in cab]]
    estilo = [("LINEBELOW", (0, 0), (-1, 0), 1, VERDE), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    criticos = set(r["meses_criticos"])
    for i, m in enumerate(r["meses"], start=1):
        ns, nc = nivel(m["prob_mes_seco"]), nivel(m["prob_mes_caliente"])
        st = E["cellb"] if m["mes"] in criticos else E["cell"]
        marca = " *" if m["mes"] in criticos else ""
        datos.append([Paragraph(_t(mes_corto(m["mes"]) + marca), st), Paragraph(_t(m["etapa"]), st),
                      Paragraph(f"{ns} ({num(100 * m['prob_mes_seco'])} %)", E["cell"]),
                      Paragraph(f"{nc} ({num(100 * m['prob_mes_caliente'])} %)", E["cell"]),
                      Paragraph(_t(f"{'+' if m['cambio_lluvia_pct'] > 0 else ''}{num(m['cambio_lluvia_pct'])} %"), E["cell"])])
        estilo += [("BACKGROUND", (2, i), (2, i), NIVEL_FONDO[ns]), ("BACKGROUND", (3, i), (3, i), NIVEL_FONDO[nc])]
    tabla = Table(datos, colWidths=[20 * mm, ancho - 20 * mm - 3 * 30 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    s += [KeepTogether([Paragraph("Mes a mes", E["h1"]),
                        Paragraph(_t("Probabilidad de que cada mes sea seco o caliente (en un clima normal es 20 %). "
                                     "La última columna es el cambio esperado en la lluvia. * = mes crítico para su lote."), E["p2"]),
                        Spacer(1, 4), tabla])]

    # --- Historia
    hist = sorted(r["eventos_historicos"], key=lambda h: -h["pico_oni"])[:5]
    if hist:
        filas = [[Paragraph(f"<b>{c}</b>", E["cell"]) for c in ("Evento", "Tipo", "Meses secos", "Meses calientes", "Índice observado")]]
        filas += [[Paragraph(h["evento"], E["cell"]), Paragraph(_t(h["clase"]), E["cell"]), Paragraph(f"{h['meses_secos']} de 12", E["cell"]),
                   Paragraph(f"{h['meses_calientes']} de 12", E["cell"]), Paragraph(num(h["indice_observado"]), E["cell"])] for h in hist]
        th = Table(filas, colWidths=[24 * mm, ancho - 24 * mm - 3 * 30 * mm, 30 * mm, 30 * mm, 30 * mm])
        th.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, VERDE), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA)]))
        s += [KeepTogether([Paragraph("Lo que pasó en su finca en Niños anteriores", E["h1"]),
                            Paragraph(_t("Datos reales de su punto en los mismos meses del año, con la misma etapa del cultivo."), E["p2"]),
                            Spacer(1, 4), th])]

    # --- Recomendaciones
    recs = [ListItem(Paragraph(_t(f"<b>{x['titulo']}.</b> {x['texto']}").replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"), E["p"]), leftIndent=16)
            for x in r["recomendaciones"]]
    s += [Paragraph("Qué hacer", E["h1"]), ListFlowable(recs, bulletType="1", leftIndent=16)]

    # --- Cómo leer / limitaciones
    notas = [
        "Cómo se calcula: se analizan más de 70 años de clima diario de su punto (lluvia, evaporación y temperatura, reanálisis ERA5-Land) "
        "y se mide cuánto cambian cuando hay El Niño. Esa probabilidad se pondera según qué tan sensible está el café cada mes.",
        "Es un escenario (qué pasaría si llega un Superniño), no un pronóstico. Consulte los boletines del IDEAM y de la FNC para saber si el evento se está formando.",
        "La sensibilidad de cada etapa del café viene de la literatura técnica (Cenicafé y otros) y es aproximada. No incluye excesos de lluvia, roya ni tipo de suelo.",
        *r["advertencias"],
    ]
    s += [KeepTogether([Paragraph("Para tener en cuenta", E["h1"]), *[Paragraph(_t("• " + n), E["small"]) for n in notas]])]

    doc.build(s, onFirstPage=_pie(fecha_larga(r["fecha_calculo"]), r["version_modelo"]),
              onLaterPages=_pie(fecha_larga(r["fecha_calculo"]), r["version_modelo"]))
    return buf.getvalue()
