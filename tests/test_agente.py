from superninio.agente import ExtractorReglas, SubagenteSuperninio, es_cancelacion, es_disparador
from superninio.datos.geocodificacion import Lugar

RES_FALSO = {"fecha_calculo": "2026-09-25"}


def _agente(geo=None, llamadas=None):
    llamadas = llamadas if llamadas is not None else []

    def calcular(entrada):
        llamadas.append(entrada)
        return {"entrada": entrada, **RES_FALSO}

    return SubagenteSuperninio(
        extractor=ExtractorReglas(),
        geocodificar_fn=geo or (lambda municipio, departamento=None, vereda=None:
                                Lugar(5.0, -75.6, "vereda" if vereda else "municipio", municipio)),
        calcular_fn=calcular,
        pdf_fn=lambda res, finca: b"%PDF-falso",
    ), llamadas


def _sin_diagnostico(monkeypatch):
    import superninio.agente.conversacion as c
    monkeypatch.setattr(c, "diagnostico", lambda r: {"mensaje_whatsapp": "Riesgo 48/100"})


def test_disparador():
    for t in ("Superniño", "superniño", "SUPER NIÑO", "súper niño por favor", "quiero el superninio", "super-nino"):
        assert es_disparador(t), t
    for t in ("hola", "el niño está enfermo", "supermercado"):
        assert not es_disparador(t), t
    assert es_cancelacion("cancelar") and es_cancelacion("  Salir ") and not es_cancelacion("no se")


def test_ignora_mensajes_sin_sesion():
    ag, _ = _agente()
    assert ag.manejar_mensaje("57300", texto="hola, ¿cómo va la cosecha?") is None


def test_flujo_completo_por_pasos(monkeypatch):
    _sin_diagnostico(monkeypatch)
    ag, llamadas = _agente()
    r = ag.manejar_mensaje("57300", texto="Superniño")
    assert "Diagnóstico Superniño" in r.texto and "Ubicación" in r.texto and ag.activo("57300")
    r = ag.manejar_mensaje("57300", ubicacion=(4.98, -75.6))
    assert "Edad" in r.texto and "Ubicación" not in r.texto
    r = ag.manejar_mensaje("57300", texto="tiene 4 años")
    assert "soqueado" in r.texto
    r = ag.manejar_mensaje("57300", texto="sí")
    assert "última zoca" in r.texto
    avisos = []
    r = ag.manejar_mensaje("57300", texto="hace 8 meses", notificar=avisos.append)
    assert r.pdf == b"%PDF-falso" and r.terminado and avisos
    assert llamadas[-1] == {"lat": 4.98, "lon": -75.6, "edad_meses": 48, "soqueado": True, "escenario": "super", "meses_desde_zoca": 8}
    assert not ag.activo("57300")


def test_todo_en_un_mensaje(monkeypatch):
    _sin_diagnostico(monkeypatch)
    ag, llamadas = _agente()
    r = ag.manejar_mensaje("1", texto="Superniño: finca en la vereda La Floresta, municipio de Chinchiná, Caldas. "
                                      "El cafetal tiene 3 años y medio y nunca lo he soqueado")
    assert r.pdf is not None
    assert llamadas[-1]["edad_meses"] == 42 and llamadas[-1]["soqueado"] is False


def test_zoca_y_edad_en_la_misma_frase(monkeypatch):
    _sin_diagnostico(monkeypatch)
    ag, llamadas = _agente()
    ag.manejar_mensaje("2", texto="superniño")
    ag.manejar_mensaje("2", ubicacion=(5.0, -75.5))
    r = ag.manejar_mensaje("2", texto="el lote tiene 7 años y lo soqueé hace 2 años")
    assert r.pdf is not None
    assert llamadas[-1]["edad_meses"] == 84 and llamadas[-1]["meses_desde_zoca"] == 24


def test_municipio_no_encontrado_pide_departamento(monkeypatch):
    _sin_diagnostico(monkeypatch)
    intentos = []

    def geo(municipio, departamento=None, vereda=None):
        intentos.append(departamento)
        return Lugar(4.5, -75.7, "municipio", municipio) if departamento else None

    ag, _ = _agente(geo=geo)
    ag.manejar_mensaje("3", texto="superniño")
    r = ag.manejar_mensaje("3", texto="en Génova")
    assert "No encontré" in r.texto and "departamento" in r.texto
    r = ag.manejar_mensaje("3", texto="Quindío")
    assert "Ubicación" not in r.texto and intentos[-1] == "Quindío"


def test_ubicacion_fuera_de_colombia():
    ag, _ = _agente()
    ag.manejar_mensaje("4", texto="Superniño")
    r = ag.manejar_mensaje("4", ubicacion=(40.4, -3.7))
    assert "no está en Colombia" in r.texto


def test_cancelar():
    ag, _ = _agente()
    ag.manejar_mensaje("5", texto="Superniño")
    r = ag.manejar_mensaje("5", texto="cancelar")
    assert r.terminado and not ag.activo("5")


def test_reinicia_con_nueva_palabra_clave():
    ag, _ = _agente()
    ag.manejar_mensaje("6", texto="Superniño")
    ag.manejar_mensaje("6", texto="tiene 2 años")
    r = ag.manejar_mensaje("6", texto="superniño")
    assert "Edad" in r.texto  # empezó de cero


def test_extractor_reglas():
    e = ExtractorReglas()
    assert e.extraer("tiene 18 meses", {})["edad_meses"] == 18
    assert e.extraer("un año y medio", {})["edad_meses"] == 18
    assert e.extraer("no lo he soqueado", {})["soqueado"] is False
    assert e.extraer("4.98, -75.60", {})["lat"] == 4.98
    assert e.extraer("no", {"ultima_pregunta": "soqueado"})["soqueado"] is False
    assert e.extraer("hace 1 año", {"ultima_pregunta": "meses_desde_zoca"})["meses_desde_zoca"] == 12
    d = e.extraer("La Floresta, Chinchiná, Caldas", {"ultima_pregunta": "ubicacion"})
    assert d["municipio"] == "Chinchina" and d["departamento"] == "Caldas"
