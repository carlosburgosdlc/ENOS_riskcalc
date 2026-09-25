from superninio.modelo.phenology import altitude_heat_factor, pattern_from_latitude, sensitivity_calendar


def _meses(y, m, n):
    return [{"y": y + (m + i) // 12, "m": (m + i) % 12} for i in range(n)]


def test_siembra_nueva():
    cal = sensitivity_calendar({"ageMonths": 2, "zoca": False, "monthsSinceZoca": 0, "pattern": "centro", "elevation": 1500}, _meses(2026, 9, 12))
    assert cal[0]["stage"].startswith("Establecimiento") and cal[0]["Sd"] == 1
    assert cal[8]["stage"].startswith("Levante")


def test_zoca_menos_sensible_que_siembra():
    z = sensitivity_calendar({"ageMonths": 80, "zoca": True, "monthsSinceZoca": 1, "pattern": "centro", "elevation": 1500}, _meses(2026, 9, 1))
    s = sensitivity_calendar({"ageMonths": 1, "zoca": False, "monthsSinceZoca": 0, "pattern": "centro", "elevation": 1500}, _meses(2026, 9, 1))
    assert "zoca" in z[0]["stage"] and z[0]["Sd"] < s[0]["Sd"]


def test_calendario_productivo_centro():
    cal = sensitivity_calendar({"ageMonths": 48, "zoca": False, "monthsSinceZoca": 0, "pattern": "centro", "elevation": 1500}, _meses(2027, 0, 12))
    assert cal[2]["stage"] == "Floración"
    assert cal[4]["stage"] == "Expansión del fruto" and cal[4]["Sd"] == 1


def test_latitud_y_altitud():
    assert [pattern_from_latitude(x) for x in (8, 5, 2)] == ["norte", "centro", "sur"]
    assert altitude_heat_factor(1100) > altitude_heat_factor(1900)
