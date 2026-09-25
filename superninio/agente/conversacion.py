"""Subagente conversacional Superniño para WhatsApp.

Uso desde el webhook de WhatsApp de AMY (el orquestador le cede el mensaje):

    agente = SubagenteSuperninio()                      # una sola instancia
    resp = agente.manejar_mensaje(chat_id, texto=..., ubicacion=(lat, lon), notificar=enviar_texto)
    if resp is None:            -> el mensaje no es para este subagente (siga el flujo normal de AMY)
    elif resp.pdf:              -> enviar resp.pdf como documento (resp.nombre_pdf) con resp.texto de pie
    else:                       -> enviar resp.texto

Mientras agente.activo(chat_id) sea True, los mensajes de ese chat deben enrutarse a este subagente.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from ..calculo import calcular_riesgo
from ..datos.clima import ErrorDatos
from ..datos.geocodificacion import Lugar, geocodificar
from ..informe import diagnostico, generar_pdf
from .disparador import es_cancelacion, es_disparador, quitar_disparador
from .extraccion import CAMPOS, Extractor, ExtractorReglas

log = logging.getLogger(__name__)

MAX_TURNOS = 8          # preguntas antes de desistir
TTL_HORAS = 24          # una sesión abandonada expira


@dataclass
class Respuesta:
    texto: str
    pdf: Optional[bytes] = None
    nombre_pdf: Optional[str] = None
    terminado: bool = False
    resultado: Optional[dict] = None  # salida completa de calcular_riesgo (para guardar en BD/analítica)


class AlmacenSesiones(Protocol):
    def obtener(self, chat_id: str) -> Optional[dict]: ...
    def guardar(self, chat_id: str, sesion: dict) -> None: ...
    def borrar(self, chat_id: str) -> None: ...


class AlmacenMemoria:
    """Sesiones en memoria. En producción con varios procesos, use Redis o la BD de AMY (misma interfaz)."""

    def __init__(self, ttl_horas: float = TTL_HORAS):
        self._d: dict[str, dict] = {}
        self._ttl = ttl_horas * 3600
        self._lock = threading.Lock()

    def obtener(self, chat_id):
        with self._lock:
            s = self._d.get(chat_id)
            if s and time.time() - s["actualizado"] > self._ttl:
                del self._d[chat_id]
                return None
            return s

    def guardar(self, chat_id, sesion):
        with self._lock:
            sesion["actualizado"] = time.time()
            self._d[chat_id] = sesion

    def borrar(self, chat_id):
        with self._lock:
            self._d.pop(chat_id, None)


# ------------------------------------------------------------------ textos
BIENVENIDA = (
    "☕ *Diagnóstico Superniño*\n"
    "Voy a calcular qué tan expuesto está su cafetal si llega un Superniño (sequía y calor fuertes). Necesito estos datos:\n\n"
)
PREGUNTAS = {
    "ubicacion": "📍 *Ubicación de la finca*: envíe su ubicación de WhatsApp (📎 > Ubicación) estando en la finca, "
                 "o escriba la *vereda y el municipio*.",
    "edad_meses": "🌱 *Edad del cafetal*: ¿cuántos años o meses tiene desde la siembra?",
    "soqueado": "✂️ *¿Ha soqueado el lote?* Si sí, ¿hace cuánto?",
    "meses_desde_zoca": "✂️ ¿Hace cuánto tiempo hizo la *última zoca*? (años o meses)",
}
CIERRE_BIENVENIDA = "\n\nPuede enviarlo todo en un solo mensaje. Escriba *cancelar* para salir."


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _en_colombia(lat: float, lon: float) -> bool:
    return -4.5 <= lat <= 13.5 and -82 <= lon <= -66


class SubagenteSuperninio:
    def __init__(
        self,
        extractor: Extractor | None = None,
        almacen: AlmacenSesiones | None = None,
        geocodificar_fn: Callable[..., Optional[Lugar]] = geocodificar,
        calcular_fn: Callable[[dict], dict] = calcular_riesgo,
        pdf_fn: Callable[[dict, dict], bytes] = generar_pdf,
        escenario: str = "super",
    ):
        if extractor is None:
            try:
                from .extraccion import ExtractorClaude
                extractor = ExtractorClaude()
            except Exception as e:  # noqa: BLE001 - sin SDK o sin credenciales: reglas
                log.warning("ExtractorClaude no disponible (%s); uso ExtractorReglas", e)
                extractor = ExtractorReglas()
        self.extractor = extractor
        self.almacen = almacen or AlmacenMemoria()
        self.geocodificar = geocodificar_fn
        self.calcular = calcular_fn
        self.generar_pdf = pdf_fn
        self.escenario = escenario

    # ------------------------------------------------------------- API pública
    def activo(self, chat_id: str) -> bool:
        return self.almacen.obtener(chat_id) is not None

    def manejar_mensaje(self, chat_id: str, texto: str | None = None,
                        ubicacion: tuple[float, float] | None = None,
                        notificar: Callable[[str], None] | None = None) -> Respuesta | None:
        sesion = self.almacen.obtener(chat_id)
        nuevo = False
        if es_disparador(texto):
            sesion = {"datos": {}, "turnos": 0, "ultima_pregunta": None, "inicio": dt.datetime.now().isoformat()}
            nuevo = True
            texto = quitar_disparador(texto)
        elif sesion is None:
            return None  # no es para este subagente

        if texto and es_cancelacion(texto):
            self.almacen.borrar(chat_id)
            return Respuesta("Listo, cancelé el diagnóstico. Cuando quiera, escriba *Superniño* para empezar de nuevo.", terminado=True)

        datos = sesion["datos"]
        if ubicacion:
            lat, lon = ubicacion
            if _en_colombia(lat, lon):
                datos.update(lat=lat, lon=lon, precision="gps")
            else:
                self.almacen.guardar(chat_id, sesion)
                return Respuesta("Esa ubicación no está en Colombia. ¿Me envía la ubicación de la finca, o la vereda y el municipio?")
        if texto and texto.strip():
            try:
                ext = self.extractor.extraer(texto, {"datos": datos, "ultima_pregunta": sesion["ultima_pregunta"]})
            except Exception:  # noqa: BLE001 - un fallo de extracción no debe tumbar la conversación
                log.exception("Fallo de extracción")
                ext = ExtractorReglas().extraer(texto, {"datos": datos, "ultima_pregunta": sesion["ultima_pregunta"]})
            if ext.get("cancelar"):
                self.almacen.borrar(chat_id)
                return Respuesta("Listo, cancelé el diagnóstico. Cuando quiera, escriba *Superniño* para empezar de nuevo.", terminado=True)
            self._fusionar(datos, ext)

        aviso = self._resolver_ubicacion(datos)
        faltan = self._faltantes(datos)
        if faltan:
            sesion["turnos"] += 1
            if sesion["turnos"] > MAX_TURNOS:
                self.almacen.borrar(chat_id)
                return Respuesta("No logré completar los datos. Si quiere, escriba *Superniño* para intentarlo de nuevo, "
                                 "o pida ayuda a su extensionista.", terminado=True)
            sesion["ultima_pregunta"] = faltan[0]
            self.almacen.guardar(chat_id, sesion)
            return Respuesta(self._pregunta(faltan, nuevo, aviso))

        # Datos completos: calcular
        self.almacen.borrar(chat_id)
        if notificar:
            notificar("⏳ Tengo todo. Estoy analizando más de 70 años de clima de su finca; esto tarda alrededor de un minuto...")
        return self._calcular_y_responder(datos)

    # ------------------------------------------------------------- internos
    @staticmethod
    def _fusionar(datos: dict, ext: dict) -> None:
        for k in CAMPOS:
            if k == "cancelar" or ext.get(k) is None:
                continue
            v = ext[k]
            if k == "municipio" and _sin_tildes(str(v)).lower() != _sin_tildes(str(datos.get("municipio") or "")).lower():
                datos.pop("geocodificado", None)
                datos.pop("municipio_no_encontrado", None)
                if datos.get("precision") in ("municipio", "vereda"):
                    datos.pop("lat", None); datos.pop("lon", None)
            if k in ("departamento", "vereda") and v != datos.get(k):
                datos.pop("municipio_no_encontrado", None)
            if k in ("lat", "lon"):
                datos["precision"] = "coordenadas"
            datos[k] = v
        if datos.get("soqueado") is False:
            datos.pop("meses_desde_zoca", None)

    def _resolver_ubicacion(self, datos: dict) -> str | None:
        if datos.get("lat") is not None and datos.get("lon") is not None:
            if not _en_colombia(datos["lat"], datos["lon"]):
                datos.pop("lat"); datos.pop("lon")
                return "Esas coordenadas no están en Colombia."
            return None
        if datos.get("municipio") and not datos.get("geocodificado") and not datos.get("municipio_no_encontrado"):
            lugar = self.geocodificar(datos["municipio"], datos.get("departamento"), datos.get("vereda"))
            if lugar is None or not _en_colombia(lugar.lat, lugar.lon):
                datos["municipio_no_encontrado"] = True
                return f"No encontré el municipio «{datos['municipio']}»."
            datos.update(lat=lugar.lat, lon=lugar.lon, precision=lugar.precision, geocodificado=True,
                         ubicacion_texto=", ".join(x for x in (
                             f"Vereda {datos['vereda']}" if datos.get("vereda") else None,
                             datos["municipio"], datos.get("departamento")) if x))
        return None

    @staticmethod
    def _faltantes(datos: dict) -> list[str]:
        f = []
        if datos.get("lat") is None:
            f.append("ubicacion")
        if datos.get("edad_meses") is None:
            f.append("edad_meses")
        if datos.get("soqueado") is None:
            f.append("soqueado")
        elif datos["soqueado"] and datos.get("meses_desde_zoca") is None:
            f.append("meses_desde_zoca")
        return f

    @staticmethod
    def _pregunta(faltan: list[str], bienvenida: bool, aviso: str | None) -> str:
        if bienvenida:
            return BIENVENIDA + "\n".join(PREGUNTAS[k] for k in faltan) + CIERRE_BIENVENIDA
        lineas = []
        if aviso:
            lineas.append(aviso)
            if "ubicacion" in faltan:
                lineas.append("¿Me dice también el *departamento*, o me comparte la ubicación de WhatsApp (📎 > Ubicación)?")
                faltan = [k for k in faltan if k != "ubicacion"]
        else:
            lineas.append("Gracias. Me falta:" if len(faltan) > 1 else "Gracias.")
        lineas += [PREGUNTAS[k] for k in faltan]
        return "\n".join(lineas)

    def _calcular_y_responder(self, datos: dict) -> Respuesta:
        entrada = {
            "lat": float(datos["lat"]), "lon": float(datos["lon"]),
            "edad_meses": int(datos["edad_meses"]), "soqueado": bool(datos["soqueado"]),
            "escenario": self.escenario,
        }
        if entrada["soqueado"]:
            entrada["meses_desde_zoca"] = int(datos["meses_desde_zoca"])
        finca = {"nombre": datos.get("nombre_finca"), "ubicacion": datos.get("ubicacion_texto"),
                 "precision": datos.get("precision")}
        try:
            resultado = self.calcular(entrada)
            pdf = self.generar_pdf(resultado, finca)
        except ErrorDatos:
            log.exception("Fallo descargando datos climáticos")
            return Respuesta("😕 No pude descargar los datos de clima en este momento. Intente de nuevo en un rato escribiendo *Superniño*.",
                             terminado=True)
        except ValueError as e:
            log.warning("Entrada inválida: %s", e)
            return Respuesta("😕 Algún dato no quedó bien. Escriba *Superniño* para empezar de nuevo.", terminado=True)
        texto = diagnostico(resultado)["mensaje_whatsapp"]
        if datos.get("precision") == "municipio":
            texto += "\n\n_Usé el centro del municipio. Para más precisión, repita enviando la ubicación de WhatsApp desde la finca._"
        return Respuesta(texto, pdf=pdf, nombre_pdf=f"diagnostico_superninio_{resultado['fecha_calculo']}.pdf",
                         terminado=True, resultado=resultado)
