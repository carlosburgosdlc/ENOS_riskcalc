// Punto de entrada único del motor de cálculo (sin interfaz).
//
//   import { calcularRiesgo } from './calcular.js';
//   const resultado = await calcularRiesgo({ lat: 4.98, lon: -75.6, edad_meses: 48, soqueado: false, escenario: 'super' });
//
// También por línea de comandos:
//   node calcular.js entrada.json      (o)      echo '{...}' | node calcular.js
//
// Entra: un objeto JSON (ver ESQUEMA_ENTRADA). Sale: un objeto JSON serializable.
// El único I/O es la descarga de clima (Open-Meteo); se puede reemplazar con opciones.obtenerClima
// para usar caché u otra fuente.
import { ONI, ONI_META } from '../data/oni.js';
import { buildDataset } from './climate.js';
import { oniTemplate, scenarioTrajectory, SCENARIOS } from './scenario.js';
import { sensitivityCalendar, patternFromLatitude, HARVEST_PATTERNS, MONTHS, cropDiagnosis } from './phenology.js';
import { computeRisk, analogs } from './risk.js';
import { fetchMonthlyClimate, fetchElevation } from './data.js';
import { recommendations } from './recommendations.js';

export const VERSION_MODELO = '1.0.0';

// JSON Schema de la entrada: se puede usar tal cual como definición de la tool del agente.
export const ESQUEMA_ENTRADA = {
  type: 'object',
  required: ['lat', 'lon', 'edad_meses', 'soqueado', 'escenario'],
  properties: {
    lat: { type: 'number', minimum: -4.5, maximum: 13.5, description: 'Latitud de la finca (Colombia)' },
    lon: { type: 'number', minimum: -82, maximum: -66, description: 'Longitud de la finca (Colombia)' },
    edad_meses: { type: 'integer', minimum: 0, maximum: 480, description: 'Edad del cafetal desde la siembra, en meses' },
    soqueado: { type: 'boolean', description: '¿El lote fue soqueado (zoca)?' },
    meses_desde_zoca: { type: 'integer', minimum: 0, maximum: 240, description: 'Obligatorio si soqueado = true' },
    escenario: { type: 'string', enum: ['moderado', 'fuerte', 'super'], description: 'Intensidad de El Niño' },
    pico_oni: { type: 'number', minimum: 0.5, maximum: 3.5, description: 'Opcional: pico ONI personalizado; reemplaza al del escenario' },
    patron_cosecha: { type: 'string', enum: ['auto', 'norte', 'centro', 'sur'], description: 'Opcional. auto = según latitud' },
    anio_evento: { type: 'integer', description: 'Opcional: año de desarrollo del evento El Niño' },
    mes_inicio: { type: 'string', pattern: '^\\d{4}-\\d{2}$', description: 'Opcional: primer mes proyectado, AAAA-MM (por defecto el mes siguiente)' },
  },
};

function validar(e) {
  const err = [];
  const num = (k) => typeof e[k] === 'number' && Number.isFinite(e[k]);
  if (!e || typeof e !== 'object') throw new Error('La entrada debe ser un objeto JSON');
  if (!num('lat') || e.lat < -4.5 || e.lat > 13.5) err.push('lat inválida (Colombia: -4.5 a 13.5)');
  if (!num('lon') || e.lon < -82 || e.lon > -66) err.push('lon inválida (Colombia: -82 a -66)');
  if (!Number.isInteger(e.edad_meses) || e.edad_meses < 0) err.push('edad_meses debe ser un entero ≥ 0');
  if (typeof e.soqueado !== 'boolean') err.push('soqueado debe ser true o false');
  if (e.soqueado === true && (!Number.isInteger(e.meses_desde_zoca) || e.meses_desde_zoca < 0)) {
    err.push('meses_desde_zoca es obligatorio (entero ≥ 0) cuando soqueado = true');
  }
  if (!SCENARIOS[e.escenario]) err.push(`escenario debe ser: ${Object.keys(SCENARIOS).join(', ')}`);
  if (e.pico_oni != null && (!num('pico_oni') || e.pico_oni < 0.5 || e.pico_oni > 3.5)) err.push('pico_oni debe estar entre 0.5 y 3.5');
  if (e.patron_cosecha != null && e.patron_cosecha !== 'auto' && !HARVEST_PATTERNS[e.patron_cosecha]) err.push('patron_cosecha inválido');
  if (e.mes_inicio != null && !/^\d{4}-\d{2}$/.test(e.mes_inicio)) err.push('mes_inicio debe tener formato AAAA-MM');
  if (err.length) throw new Error(`Entrada inválida: ${err.join('; ')}`);
}

const r = (v, d = 3) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);
const textoPlano = (html) => html.replace(/<[^>]+>/g, '');

/**
 * @param {object} entrada  ver ESQUEMA_ENTRADA
 * @param {object} [opciones]
 * @param {(lat:number, lon:number) => Promise<{model:string, end:string, monthly:Array}>} [opciones.obtenerClima]
 * @param {(lat:number, lon:number) => Promise<number|null>} [opciones.obtenerElevacion]
 * @param {number} [opciones.replicas=1000]  réplicas bootstrap
 * @param {Date} [opciones.hoy]
 */
export async function calcularRiesgo(entrada, opciones = {}) {
  validar(entrada);
  const {
    obtenerClima = fetchMonthlyClimate,
    obtenerElevacion = fetchElevation,
    replicas = 1000,
    hoy = new Date(),
  } = opciones;
  const { lat, lon } = entrada;

  // 1. Datos externos (único paso con I/O)
  const [clima, elevacion] = await Promise.all([obtenerClima(lat, lon), obtenerElevacion(lat, lon)]);

  // 2. Cultivo
  const patron = !entrada.patron_cosecha || entrada.patron_cosecha === 'auto' ? patternFromLatitude(lat) : entrada.patron_cosecha;
  const cultivo = {
    ageMonths: entrada.edad_meses,
    zoca: entrada.soqueado,
    monthsSinceZoca: entrada.soqueado ? entrada.meses_desde_zoca : 0,
    pattern: patron,
    elevation: elevacion,
  };

  // 3. Escenario: trayectoria del ONI para los próximos 12 meses
  const pico = entrada.pico_oni ?? SCENARIOS[entrada.escenario].peak;
  let inicioY, inicioM;
  if (entrada.mes_inicio) {
    [inicioY, inicioM] = entrada.mes_inicio.split('-').map(Number);
    inicioM -= 1;
  } else {
    const sig = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 1);
    inicioY = sig.getFullYear();
    inicioM = sig.getMonth();
  }
  const anioEvento = entrada.anio_evento ?? (hoy.getMonth() >= 2 ? hoy.getFullYear() : hoy.getFullYear() - 1);
  const plantilla = oniTemplate(ONI, 1.5);
  const trayectoria = scenarioTrajectory(plantilla, pico, anioEvento, inicioY, inicioM);

  // 4. Modelo: amenaza (regresiones + bootstrap) × vulnerabilidad (fenología)
  const dataset = buildDataset(clima.monthly, ONI);
  const calendario = sensitivityCalendar(cultivo, trayectoria);
  const res = computeRisk(dataset, trayectoria, calendario, { B: replicas });
  const hist = analogs(dataset, plantilla.events, trayectoria, calendario, anioEvento);

  // 5. Salida JSON
  const advertencias = cropDiagnosis(cultivo);
  if (ONI_META.provisional) advertencias.push('Serie ONI provisional: ejecutar scripts/update_oni.py antes de usar en producción.');
  if (clima.model !== 'era5_land') advertencias.push('ERA5-Land no disponible; se usó ERA5 (menor resolución).');
  if (!res.significant) advertencias.push('La señal de El Niño no es estadísticamente significativa en esta ubicación: el aumento de riesgo no se distingue de la variabilidad natural.');

  return {
    version_modelo: VERSION_MODELO,
    entrada: { ...entrada, patron_cosecha: patron, pico_oni: pico, anio_evento: anioEvento },
    ubicacion: { lat, lon, elevacion_m: elevacion, fuente_clima: clima.model, datos_hasta: clima.end, anios_analizados: res.yearsRange },
    indice: {
      valor: r(res.irc, 1),
      categoria: res.category.label,
      ic90: [r(res.ci[0], 1), r(res.ci[1], 1)],
      valor_anio_neutro: r(res.ircNeutral, 1),
      categoria_anio_neutro: res.categoryNeutral.label,
      aumento: r(res.delta, 1),
      aumento_ic90: [r(res.ciDelta[0], 1), r(res.ciDelta[1], 1)],
      riesgo_relativo: r(res.ratio, 2),
      p_valor: r(res.pBoot, 4),
      significativo: res.significant,
      replicas_bootstrap: res.nBoot,
      interpretacion: 'Probabilidad media (0-100) de mes seco o caliente, ponderada por la sensibilidad de la etapa del cultivo. Clima normal ≈ 20.',
    },
    meses: res.months.map((m) => ({
      mes: `${m.y}-${String(m.m + 1).padStart(2, '0')}`,
      etiqueta: `${MONTHS[m.m]} ${m.y}`,
      oni: r(m.oni, 2),
      etapa: m.stage,
      sensibilidad_sequia: r(m.Sd, 2),
      sensibilidad_calor: r(m.Sh, 2),
      prob_mes_seco: r(m.pDry),
      prob_mes_seco_neutro: r(m.pDryNeutral),
      prob_mes_caliente: r(m.pHot),
      prob_mes_caliente_neutro: r(m.pHotNeutral),
      cambio_lluvia_pct: r(m.dPpct, 1),
      cambio_tmax_c: r(m.dTmax, 2),
      senal_sequia_significativa: m.qSlopeD < 0.05,
      senal_calor_significativa: m.qSlopeT < 0.05,
    })),
    eventos_historicos: hist.filter((a) => a.available).map((a) => ({
      evento: `${a.year0}-${a.year0 + 1}`,
      pico_oni: a.peak,
      clase: a.class,
      indice_observado: r(a.ircObserved, 1),
      meses_secos: a.dryMonths,
      meses_calientes: a.hotMonths,
    })),
    recomendaciones: recommendations(res, cultivo).map(textoPlano),
    advertencias,
  };
}

// Uso por línea de comandos: node calcular.js entrada.json  |  echo '{...}' | node calcular.js
const esCLI = typeof process !== 'undefined' && process.argv?.[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href;
if (esCLI) {
  const fs = await import('node:fs');
  const raw = process.argv[2] ? fs.readFileSync(process.argv[2], 'utf8') : fs.readFileSync(0, 'utf8');
  try {
    console.log(JSON.stringify(await calcularRiesgo(JSON.parse(raw)), null, 2));
  } catch (e) {
    console.error(JSON.stringify({ error: e.message }));
    process.exit(1);
  }
}
