import io

from pypdf import PdfReader

from superninio.calculo import calcular_riesgo
from superninio.informe import diagnostico, generar_pdf

from .conftest import HOY, clima_sintetico

CLIMA = clima_sintetico(-0.6, 0.6, 11)


def _res(**cambios):
    entrada = {"lat": 4.98, "lon": -75.6, "edad_meses": 48, "soqueado": False, "escenario": "super", **cambios}
    return calcular_riesgo(entrada, obtener_clima_fn=lambda *_: CLIMA, obtener_elevacion_fn=lambda *_: 1250, replicas=200, hoy=HOY)


def test_diagnostico_explica_resultado():
    d = diagnostico(_res())
    assert "Superniño" in d["titular"]
    assert any(r.startswith("Menos lluvia") for r in d["razones"])
    assert any(r.startswith("Altitud") for r in d["razones"])
    assert "confiable" in d["confianza"]
    assert "/100" in d["mensaje_whatsapp"]


def test_diagnostico_zoca_y_joven():
    assert any(r.startswith("Zoca") for r in diagnostico(_res(soqueado=True, meses_desde_zoca=3, edad_meses=90))["razones"])
    assert any(r.startswith("Cafetal joven") for r in diagnostico(_res(edad_meses=4))["razones"])


def test_pdf_valido_y_legible():
    r = _res()
    pdf = generar_pdf(r, {"nombre": "La Esperanza", "ubicacion": "Vereda La Floresta, Chinchiná, Caldas", "precision": "vereda"})
    lector = PdfReader(io.BytesIO(pdf))
    assert 1 <= len(lector.pages) <= 4
    texto = " ".join(p.extract_text() for p in lector.pages)
    for esperado in ("Diagnóstico Superniño", "¿Por qué obtuvo esta nota?", "Mes a mes", "Qué hacer", "Chinchiná"):
        assert esperado in texto
    assert f"{r['indice']['valor']:.0f}" in texto
    assert "update_oni" not in texto  # advertencias técnicas no llegan al caficultor
