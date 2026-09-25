# Integración con AMY (WhatsApp)

El paquete `superninio` se entrega como **un subagente listo para conectar** al webhook de WhatsApp de AMY.
Se activa cuando el caficultor escribe **"Superniño"**, pide los datos que faltan, calcula el índice y
responde con un **PDF** (diagnóstico, explicación del resultado y recomendaciones).

## Instalación

```bash
pip install -e .            # Python >= 3.10. Dependencias: numpy, reportlab, anthropic, pydantic
pytest -q                   # opcional: pip install -e ".[dev]"
```

## Variables de entorno

| Variable | Obligatoria | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sí (recomendado) | Extracción de datos del texto con Claude. Sin ella, el subagente usa un extractor por reglas, más limitado. |
| `SUPERNINIO_MODELO` | No | Modelo de Claude para la extracción (por defecto `claude-opus-5`). |
| `OPEN_METEO_API_KEY` | **Sí en producción** | La API gratuita de Open-Meteo es solo para uso no comercial. Con la clave se usa el endpoint `customer-*`. |
| `SUPERNINIO_CACHE_DIR` | Recomendada | Carpeta de caché del clima por punto (evita descargar 75 años en cada consulta). |
| `NOMINATIM_USER_AGENT` | Recomendada | Identificación exigida por la política de Nominatim, p. ej. `SUA-AMY/1.0 (correo@empresa.com)`. |

## Conexión con el webhook

```python
from superninio.agente import SubagenteSuperninio

agente = SubagenteSuperninio()          # una instancia por proceso

def on_whatsapp_message(chat_id, texto=None, ubicacion=None):
    # 1. ¿Es para el subagente? (contiene "Superniño" o hay una sesión abierta en este chat)
    resp = agente.manejar_mensaje(
        chat_id,
        texto=texto,                               # texto del mensaje (o None)
        ubicacion=ubicacion,                       # (lat, lon) si el caficultor compartió su ubicación
        notificar=lambda t: enviar_texto(chat_id, t),  # aviso "estoy calculando..." antes del cálculo (~30-60 s)
    )
    if resp is None:
        return orquestador_amy(chat_id, texto)     # no era para el subagente: flujo normal de AMY

    if resp.pdf:
        enviar_documento(chat_id, resp.pdf, nombre=resp.nombre_pdf, pie=resp.texto)
        guardar_resultado(chat_id, resp.resultado)  # opcional: dict completo para analítica / CRM
    else:
        enviar_texto(chat_id, resp.texto)
```

- `enviar_texto` / `enviar_documento` son las funciones que AMY ya usa con su proveedor de WhatsApp
  (Meta Cloud API, Twilio, etc.). En la Cloud API de Meta el PDF se sube a `/media` y se envía como `document`.
- **Enrutamiento:** mientras `agente.activo(chat_id)` sea `True`, los mensajes de ese chat deben ir al subagente
  y no al orquestador. `manejar_mensaje` devuelve `None` para cualquier mensaje que no le corresponde.
- **Sesiones:** por defecto se guardan en memoria (expiran a las 24 h). Con varios procesos o réplicas,
  implemente la interfaz `AlmacenSesiones` (`obtener` / `guardar` / `borrar`) sobre Redis o la base de datos
  de AMY y pásela así: `SubagenteSuperninio(almacen=MiAlmacen())`.
- **Tiempo:** la primera consulta de un punto tarda ~30-60 s (descarga de clima). Ejecute `manejar_mensaje`
  en un worker/cola si el webhook tiene timeout corto; con caché baja a ~5 s.

## Conversación

```
Caficultor: Superniño
AMY:        ☕ Diagnóstico Superniño ... Necesito estos datos:
            📍 Ubicación de la finca (compartir ubicación, o vereda y municipio)
            🌱 Edad del cafetal
            ✂️ ¿Ha soqueado el lote? Si sí, ¿hace cuánto?
Caficultor: [comparte ubicación]
AMY:        Gracias. Me falta: 🌱 Edad ... ✂️ ¿Ha soqueado...?
Caficultor: tiene 7 años y lo soqueé hace 2 años
AMY:        ⏳ Tengo todo. Estoy analizando más de 70 años de clima de su finca...
AMY:        [PDF] ☕ Diagnóstico Superniño · Riesgo de su cafetal: 47/100 (Alto) ...
```

- El caficultor puede enviar todo en un solo mensaje. Escribir **cancelar** sale del flujo.
  Escribir "Superniño" de nuevo reinicia la conversación.
- Si la vereda no está en OpenStreetMap se usa el centro del municipio y el mensaje final lo advierte.
  **La ubicación compartida desde la finca es siempre la mejor opción.**
- Tras 8 intentos sin completar los datos, el subagente se despide y libera el chat.

## Diseño: qué hace el LLM y qué no

| Paso | Quién lo hace |
|---|---|
| Entender el texto libre ("mi cafetal tiene año y medio, nunca lo he soqueado") | **Claude** (`ExtractorClaude`, salida estructurada validada con Pydantic, esfuerzo `low`) |
| Decidir qué falta y qué preguntar | Código determinista (`conversacion.py`) |
| Calcular el índice | Código determinista (`superninio.calculo`) |
| Redactar el diagnóstico y el PDF | Plantillas deterministas (`superninio.informe`) |

El LLM **nunca produce números del diagnóstico**: así el resultado es reproducible y no puede inventar
cifras. Si la API de Claude falla o rechaza una solicitud, se usa el extractor por reglas. La llamada
activa `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) para que un rechazo de clasificadores
se reintente en otro modelo en el servidor.

## Usar solo el motor (sin conversación)

```python
from superninio import calcular_riesgo
from superninio.informe import generar_pdf, diagnostico

r = calcular_riesgo({"lat": 4.98, "lon": -75.6, "edad_meses": 48, "soqueado": False, "escenario": "super"})
pdf = generar_pdf(r, {"nombre": "La Esperanza", "ubicacion": "Vereda La Floresta, Chinchiná", "precision": "vereda"})
texto = diagnostico(r)["mensaje_whatsapp"]
```

CLI: `echo '{"lat":4.98,"lon":-75.6,"edad_meses":48,"soqueado":false,"escenario":"super"}' | python -m superninio.calculo`

`superninio.ESQUEMA_ENTRADA` es el JSON Schema de la entrada, por si el orquestador prefiere llamar al motor como tool.

## Salida de `calcular_riesgo` (resumen)

| Clave | Contenido |
|---|---|
| `indice` | `valor` (0-100), `categoria`, `ic90`, `valor_anio_neutro`, `riesgo_relativo`, `p_valor`, `significativo` |
| `meses` | 12 meses: `etapa`, `prob_mes_seco`, `prob_mes_caliente` (y su valor en año neutro), `cambio_lluvia_pct`, `cambio_tmax_c`, significancia |
| `meses_criticos` | Los 3 meses de mayor riesgo para el lote |
| `eventos_historicos` | Qué pasó realmente en el punto en los Niños fuertes desde 1950 |
| `recomendaciones` | `[{tema, titulo, texto}]` |
| `advertencias` | Para el caficultor (edad, altitud atípica, señal no significativa) |
| `advertencias_tecnicas` | Solo para el equipo (ONI provisional, fuente de clima de respaldo). **No mostrar al caficultor.** |

## Antes de producción

1. Ejecutar la Action **Actualizar ONI (NOAA CPC)** (la serie incluida es provisional). Mientras tanto,
   `advertencias_tecnicas` lo indica en cada resultado.
2. Contratar el plan comercial de Open-Meteo y configurar `OPEN_METEO_API_KEY`.
3. Configurar `SUPERNINIO_CACHE_DIR` en un volumen persistente.
4. Probar con 3-5 fincas reales conocidas y comparar con lo que el caficultor vivió en 2015-16 o 2023-24.
