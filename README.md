# Superniño · Riesgo climático del café ante El Niño

Paquete Python que calcula el **Índice de Riesgo Climático para Café (IRCC, 0-100)** de una finca
colombiana ante un escenario de El Niño / Superniño y lo entrega al caficultor por **WhatsApp** (AMY)
como un **PDF** con el diagnóstico, la explicación del resultado y recomendaciones de manejo.

- **Integración con AMY / WhatsApp:** ver [INTEGRACION.md](INTEGRACION.md).
- **Probar:** `pip install -e ".[dev]" && pytest -q`

## Estructura

```
superninio/
  calculo.py              calcular_riesgo(entrada) -> dict   (punto de entrada del motor, CLI)
  modelo/                 motor de cálculo puro (sin I/O)
    stats.py              OLS, t de Student, Benjamini-Hochberg, bootstrap reproducible
    climate.py            diario -> mensual, balance hídrico D3, anomalías z
    scenario.py           eventos El Niño históricos y trayectoria del ONI del escenario
    phenology.py          etapas del café y pesos de sensibilidad
    risk.py               regresiones por mes, probabilidades, IRCC, bootstrap, análogos
    recommendations.py    recomendaciones de manejo
  datos/
    clima.py              Open-Meteo (ERA5-Land, altitud) con caché
    geocodificacion.py    Nominatim (vereda / municipio)
    oni.py, oni.json      serie ONI (NOAA CPC)
  informe/
    diagnostico.py        explicación en lenguaje sencillo ("¿por qué obtuvo esta nota?")
    pdf.py                reporte PDF para el caficultor
  agente/
    disparador.py         detecta "Superniño" y "cancelar"
    extraccion.py         extrae datos del texto libre (Claude; respaldo por reglas)
    conversacion.py       SubagenteSuperninio: diálogo, cálculo y respuesta con PDF
scripts/update_oni.py     actualiza el ONI desde NOAA (GitHub Action mensual)
tests/                    pytest: estadística, modelo, paridad con la versión JS, PDF, agente
```

## Metodología

Marco de riesgo del IPCC: **riesgo = amenaza × vulnerabilidad**.

**1. Datos.** Clima diario ERA5-Land (~9 km) del punto desde 1950 vía Open-Meteo: lluvia, ET0 FAO-56 y
temperatura máxima. ONI de NOAA CPC. Altitud del DEM Copernicus 90 m.

**2. Amenaza.** Por mes calendario se construyen D3 = Σ(P − ET0) de 3 meses (tipo SPEI-3) y Tmax,
estandarizados contra la normal 1991-2020, y se ajusta:

```
z = b0 + b1·ONI + b2·(año − 2000)/10 + e
```

`b1` es la señal de El Niño en la finca; `b2` separa la tendencia de calentamiento. La probabilidad de mes
seco, P(z_D3 < −0,84), o caliente, P(z_T > +0,84), sale de la distribución empírica de residuos inflada
por la incertidumbre de parámetros. Las pendientes se prueban con t y corrección Benjamini-Hochberg.

**3. Escenario.** Trayectoria del ONI = forma media de los Niños con pico ≥ 1,5 desde 1950, escalada al
pico del escenario (moderado 1,2 · fuerte 1,8 · Superniño 2,4).

**4. Vulnerabilidad.** Peso de sensibilidad a sequía (Sd) y calor (Sh) según la etapa del cultivo cada mes
(edad, zoca, calendario de cosecha por latitud) y la altitud. Pesos tomados de la literatura
(Camargo & Camargo 2001; DaMatta & Ramalho 2006; Arcila et al. 2007, Cenicafé; Jaramillo et al. 2009, 2011):
son **supuestos expertos, no parámetros estimados**.

| Etapa | Sd | Sh |
|---|---|---|
| Establecimiento (0-6 meses) | 1,00 | 0,60 |
| Levante (6-18 meses) | 0,75 | 0,45 |
| Rebrote de zoca / chupones | 0,55 / 0,50 | 0,40 / 0,35 |
| Diferenciación floral | 0,30 | 0,40 |
| Floración | 0,85 | 0,90 |
| Expansión del fruto | 1,00 | 0,60 |
| Llenado del grano | 0,90 | 0,75 |
| Maduración y cosecha | 0,45 | 0,80 |
| Vegetativo | 0,35 | 0,30 |

**5. Índice.**

```
IRCC = 100 · Σ(Sd·P_seco + Sh·P_calor) / Σ(Sd + Sh)      (12 meses proyectados)
```

Categorías: < 25 bajo · 25-35 moderado · 35-50 alto · ≥ 50 muy alto. Se compara con el mismo cafetal en
año neutro (ONI = 0); IC 90 % y p-valor por bootstrap de años completos (1000 réplicas, semilla fija).
Los análogos recalculan el índice con lo que realmente ocurrió en el punto en 1997-98, 2015-16, etc.

**Validación del código.** Con clima simulado usando el ONI real: sin efecto, la tasa de falsos positivos
de b1 queda entre 2 % y 9 % (α = 5 %); con efecto, el modelo recupera la señal y el bootstrap la declara
significativa. El port a Python reproduce exactamente la implementación JavaScript original
(`tests/test_paridad_js.py`, referencias en `tests/fixtures/referencia_js.json`).

## Limitaciones

1. La significancia estadística aplica a la **amenaza climática**, no al daño en producción. Calibrar los
   pesos fenológicos requiere datos de rendimiento (p. ej. EVA municipales o registros de fincas).
2. ERA5-Land subestima la lluvia convectiva andina; trabajar con anomalías reduce el sesgo medio. Validar
   contra estaciones IDEAM o CHIRPS es el siguiente paso.
3. Solo seis eventos con ONI ≥ 2,0 desde 1950: por eso se usa regresión sobre todo el rango del ONI
   (supone respuesta aproximadamente lineal).
4. Es un **escenario** ("si llega un Superniño"), no un pronóstico.
5. Solo sequía y calor: no modela excesos de lluvia (La Niña), roya, heladas ni suelos.
6. La serie ONI incluida es provisional hasta ejecutar `scripts/update_oni.py` (Action mensual).
