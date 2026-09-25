# Riesgo climático del café ante El Niño / Super Niño

Aplicación web estática (sin servidor) que estima, para un punto concreto de una finca cafetera
en Colombia, el **Índice de Riesgo Climático para Café (IRCC, 0–100)** bajo un escenario de
El Niño moderado, fuerte o Super Niño, combinando:

1. **Amenaza local condicionada a ENOS**: 75 años de reanálisis diario ERA5-Land en el punto de la finca, relacionados estadísticamente con el ONI.
2. **Vulnerabilidad fenológica**: etapa del cafetal mes a mes según edad, zoca, patrón de cosecha (latitud) y altitud.

El usuario indica departamento/municipio/vereda o marca su lote en el mapa (OSM o satélite, o GPS), la edad del cultivo y si fue soqueado.

## Ejecutar

```bash
npm start          # sirve en http://localhost:8000 (python3 -m http.server)
npm test           # 15 pruebas: estadística, calibración del error tipo I, fenología, escenario
```

Despliegue: cualquier hosting estático (GitHub Pages: *Settings → Pages → Deploy from branch*).
Todo el cálculo corre en el navegador; no hay backend ni API keys.

**Antes de usar resultados reales:** ejecute la acción *Actualizar ONI (NOAA CPC)* (pestaña Actions → Run workflow).
La serie ONI incluida en `data/oni.js` es una transcripción provisional (1950–2024) y la app muestra un aviso hasta que se regenere desde NOAA con `scripts/update_oni.py`. La acción corre además cada mes.

## Uso sin interfaz (integración con agentes)

`js/calcular.js` expone una sola función: entra JSON, sale JSON.

```js
import { calcularRiesgo, ESQUEMA_ENTRADA } from './js/calcular.js';
const out = await calcularRiesgo({ lat: 4.98, lon: -75.6, edad_meses: 48, soqueado: false, escenario: 'super' });
// out.indice.valor, out.indice.significativo, out.meses[12], out.eventos_historicos, out.recomendaciones, out.advertencias
```

- CLI: `echo '{"lat":4.98,"lon":-75.6,"edad_meses":48,"soqueado":false,"escenario":"super"}' | node js/calcular.js`
- `ESQUEMA_ENTRADA` es un JSON Schema listo para usarse como definición de la tool del agente.
- `calcularRiesgo(entrada, { obtenerClima })` permite inyectar caché u otra fuente de clima; es el único paso con I/O.
- Determinista (bootstrap con semilla fija). Errores de validación con mensaje explícito.

## Metodología

### 1. Datos
| Variable | Fuente | Resolución |
|---|---|---|
| Lluvia, ET0 FAO-56, Tmax diarias 1950–hoy | ERA5-Land vía [Open-Meteo Historical API](https://open-meteo.com/en/docs/historical-weather-api) (respaldo: ERA5) | ~9 km |
| Altitud del lote | Open-Meteo Elevation (DEM Copernicus 90 m) | 90 m |
| ONI (trimestres móviles) | NOAA CPC, ERSSTv5 | mensual |
| Geocodificación de vereda/municipio | Nominatim / OpenStreetMap | — |

### 2. Variables de amenaza
- **D3**: balance hídrico climático acumulado 3 meses, Σ(P − ET0), análogo a SPEI-3.
- **Tmax**: media mensual de la temperatura máxima.
- Ambas estandarizadas por mes calendario con la normal OMM 1991–2020 → `z`.

### 3. Modelo ENOS (por cada mes calendario, ~74 años)
```
z(año) = b0 + b1·ONI + b2·(año − 2000)/10 + e
```
- El ONI usado es el del trimestre que coincide con la ventana de D3 (rezago de 1 mes para Tmax).
- `b2` absorbe la tendencia de calentamiento para no atribuirla a El Niño, y permite proyectar al año actual.
- **Probabilidad de mes seco** = P(z_D3 < −0,84) y **de mes caliente** = P(z_Tmax > +0,84) (percentiles 20/80),
  calculadas con la **distribución empírica de residuos** (no se supone normalidad), inflada por la incertidumbre de parámetros √(n/df·(1+h₀)).
- **Significancia por mes**: prueba t de `b1`, con control de la tasa de falsos descubrimientos (Benjamini-Hochberg, 24 pruebas).

### 4. Escenario
Trayectoria mensual del ONI = forma media normalizada de los Niños con pico ≥ 1,5 desde 1950 (definición NOAA: ONI ≥ 0,5 durante ≥ 5 trimestres), escalada al pico del escenario (1,2 / 1,8 / 2,4 o valor personalizado) y alineada con el año de desarrollo del evento.

### 5. Vulnerabilidad fenológica (`js/phenology.js`)
Pesos de sensibilidad a sequía (Sd) y calor (Sh), 0–1:

| Etapa | Sd | Sh |
|---|---|---|
| Establecimiento (0–6 meses de siembra) | 1,00 | 0,60 |
| Levante (6–18 meses) | 0,75 | 0,45 |
| Rebrote de zoca (0–6 meses) | 0,55 | 0,40 |
| Chupones (6–18 meses post-zoca) | 0,50 | 0,35 |
| Diferenciación floral (F−2, F−1) | 0,30 | 0,40 |
| Floración (F) | 0,85 | 0,90 |
| Expansión del fruto (F+1 a F+3) | 1,00 | 0,60 |
| Llenado del grano (F+4, F+5) | 0,90 | 0,75 |
| Maduración y cosecha (F+6 a F+8) | 0,45 | 0,80 |
| Vegetativo | 0,35 | 0,30 |

- F = mes de floración = mes pico de cosecha − 8 (~32 semanas). Patrón de cosecha por latitud (norte > 7°N, centro 3,5–7°N, sur < 3,5°N) o elegido por el usuario; la cosecha secundaria (mitaca/traviesa) pondera 0,5–0,6.
- Modificadores: primer año productivo de siembra nueva ×1,1 (raíz superficial); cafetal envejecido (> 7 años o > 5 post-zoca) ×1,1; calor por altitud (< 1300 m ×1,25; > 1700 m ×0,85).
- Referencias: Camargo & Camargo (2001) *Bragantia* 60(1); DaMatta & Ramalho (2006) *Braz. J. Plant Physiol.* 18(1); Arcila et al. (2007) *Sistemas de producción de café en Colombia*, Cenicafé; Jaramillo et al. (2009, 2011) *PLoS ONE* (broca y temperatura).

### 6. Índice
```
IRCC = 100 · Σ_m (Sd_m·P_seco,m + Sh_m·P_calor,m) / Σ_m (Sd_m + Sh_m)
```
Probabilidad media de mes estresante, ponderada por fenología, en los 12 meses proyectados. En un clima estacionario ≈ 20.
Categorías: < 25 bajo · 25–35 moderado · 35–50 alto · ≥ 50 muy alto.

Se reporta además el IRCC del **mismo cafetal en año neutro** (ONI = 0) y la diferencia:
- **IC 90 %** y **p-valor** por bootstrap de años completos (1000 réplicas, conserva la dependencia entre meses de un mismo año). H₀: el escenario no aumenta el riesgo frente al año neutro.
- **Análogos observados**: IRCC calculado con lo que *realmente ocurrió* en el punto durante 1957-58, 1965-66, 1972-73, 1982-83, 1987-88, 1991-92, 1997-98, 2009-10, 2015-16 y 2023-24.

### Validación del código
`tests/model.test.mjs` simula clima con y sin efecto ENOS usando la serie ONI real:
- sin efecto, la tasa de rechazo de `b1` a α = 0,05 está entre 2 % y 9 % (calibración del error tipo I);
- con efecto, el modelo recupera la señal, el IRCC del escenario supera al neutro y el bootstrap lo declara significativo;
- con ruido puro, la diferencia escenario − neutro es < 6 puntos.

## Limitaciones (léalas)
1. **Los pesos fenológicos son supuestos expertos**, no parámetros estimados. La significancia estadística se aplica a la **amenaza** (señal ENOS en el clima local), no al daño en rendimiento. Para calibrar la vulnerabilidad hacen falta series de producción por lote/municipio (p. ej. FNC, EVA municipales) y un modelo de rendimiento.
2. **ERA5-Land subestima la lluvia convectiva en la zona andina** y suaviza la topografía a ~9 km. Se trabaja con anomalías estandarizadas, lo que corrige gran parte del sesgo medio, pero no la variabilidad mal representada. Validar contra estaciones IDEAM o CHIRPS (0,05°) es el siguiente paso.
3. **Pocos eventos Super Niño** (ONI ≥ 2,0: seis desde 1950). Por eso el modelo usa todo el rango de ONI (regresión lineal) en lugar de promediar solo esos eventos; supone que la respuesta es aproximadamente lineal en el ONI.
4. El modelo es de **escenario** ("si llega un Super Niño"), no un pronóstico. La probabilidad de que ocurra debe tomarse de NOAA CPC / IRI / IDEAM.
5. Solo sequía y calor. No modela excesos de lluvia (La Niña), roya, heladas ni suelos (capacidad de retención de agua).
6. Uso comercial: la API gratuita de Open-Meteo es para uso no comercial; un producto comercial requiere su plan pago o datos propios (p. ej. Earth Engine/CHIRPS precomputado).

## Estructura
```
index.html, css/styles.css
js/calcular.js        punto de entrada único (JSON → JSON, CLI)
js/stats.js           OLS, t de Student, BH-FDR, bootstrap (sin dependencias)
js/climate.js         diario → mensual, D3, estandarización
js/scenario.js        eventos El Niño, plantilla y trayectoria del ONI
js/phenology.js       etapas y sensibilidad del café
js/risk.js            modelo de amenaza, IRCC, bootstrap, análogos
js/recommendations.js recomendaciones de manejo
js/data.js            Open-Meteo, Nominatim
data/oni.js           serie ONI (generada)
scripts/update_oni.py actualizador desde NOAA CPC
tests/                pruebas con node:test
```
