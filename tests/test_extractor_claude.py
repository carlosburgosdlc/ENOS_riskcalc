"""Verifica la llamada real del SDK de Anthropic contra un servidor HTTP local (sin red ni costo)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import pytest

from superninio.agente.extraccion import ExtractorClaude

RECIBIDO: dict = {}


def _servidor(respuesta: dict, status: int = 200):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            cuerpo = self.rfile.read(int(self.headers["content-length"]))
            RECIBIDO.update(path=self.path, body=json.loads(cuerpo), beta=self.headers.get("anthropic-beta"))
            data = json.dumps(respuesta).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _mensaje(texto: str, stop="end_turn") -> dict:
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5", "stop_reason": stop,
            "stop_sequence": None, "content": [{"type": "text", "text": texto}],
            "usage": {"input_tokens": 10, "output_tokens": 10}}


@pytest.fixture
def cliente():
    def crear(respuesta, status=200):
        srv = _servidor(respuesta, status)
        return anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{srv.server_port}", max_retries=0)
    return crear


def test_extraccion_estructurada(cliente):
    datos = {"municipio": "Chinchiná", "departamento": "Caldas", "vereda": "La Floresta", "lat": None, "lon": None,
             "edad_meses": 42, "soqueado": False, "meses_desde_zoca": None, "nombre_finca": None, "cancelar": False}
    ext = ExtractorClaude(client=cliente(_mensaje(json.dumps(datos))))
    out = ext.extraer("vereda La Floresta de Chinchiná, 3 años y medio, sin zoca", {"datos": {}, "ultima_pregunta": "ubicacion"})
    assert out == {"municipio": "Chinchiná", "departamento": "Caldas", "vereda": "La Floresta", "edad_meses": 42, "soqueado": False}
    b = RECIBIDO["body"]
    assert RECIBIDO["path"].startswith("/v1/messages")
    assert b["model"] == "claude-opus-5" and b["fallbacks"] == "default"
    assert b["output_config"]["effort"] == "low" and b["output_config"]["format"]["type"] == "json_schema"
    assert "server-side-fallback-2026-07-01" in RECIBIDO["beta"]
    assert "Última pregunta hecha: ubicacion" in b["messages"][0]["content"]


def test_soqueado_false_se_conserva(cliente):
    datos = {"soqueado": False, "cancelar": False}
    out = ExtractorClaude(client=cliente(_mensaje(json.dumps(datos)))).extraer("no", {"datos": {}})
    # False en soqueado es información: no debe descartarse.
    assert out.get("soqueado") is False


def test_error_de_api_usa_reglas(cliente):
    err = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
    out = ExtractorClaude(client=cliente(err, status=529)).extraer("tiene 2 años", {"datos": {}})
    assert out["edad_meses"] == 24
