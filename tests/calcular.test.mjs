import test from 'node:test';
import assert from 'node:assert/strict';
import { ONI } from '../data/oni.js';
import { oniAt } from '../js/climate.js';
import { rng, randn } from '../js/stats.js';
import { calcularRiesgo, ESQUEMA_ENTRADA } from '../js/calcular.js';

// Clima sintético inyectado: no hay llamadas de red en los tests.
function climaFalso() {
  const g = rng(5);
  const monthly = [];
  for (let y = 1950; y <= 2025; y++) {
    for (let m = 0; m < 12; m++) {
      const o = oniAt(ONI, y, m) ?? 0;
      monthly.push({ y, m, P: Math.max(0, 180 + 50 * (-0.5 * o + randn(g))), ET0: 110 + 5 * randn(g), Tmax: 24 + 0.8 * (0.5 * o + randn(g)) });
    }
  }
  return { model: 'era5_land', end: '2025-12-31', monthly };
}
const opciones = { obtenerClima: async () => climaFalso(), obtenerElevacion: async () => 1500, replicas: 200, hoy: new Date(2026, 8, 25) };
const base = { lat: 4.98, lon: -75.6, edad_meses: 48, soqueado: false, escenario: 'super' };

test('calcularRiesgo devuelve el contrato JSON completo', async () => {
  const out = await calcularRiesgo(base, opciones);
  assert.equal(out.meses.length, 12);
  assert.equal(out.meses[0].mes, '2026-10');
  assert.ok(out.indice.valor > out.indice.valor_anio_neutro);
  assert.equal(typeof out.indice.significativo, 'boolean');
  assert.ok(out.recomendaciones.every((t) => !/<[^>]+>/.test(t)), 'recomendaciones sin HTML');
  assert.equal(out.entrada.patron_cosecha, 'centro');
  assert.deepEqual(JSON.parse(JSON.stringify(out)), out); // serializable
});

test('es determinista', async () => {
  const a = await calcularRiesgo(base, opciones);
  const b = await calcularRiesgo(base, opciones);
  assert.deepEqual(a, b);
});

test('valida la entrada con errores claros', async () => {
  await assert.rejects(calcularRiesgo({ ...base, lat: 40 }, opciones), /lat inválida/);
  await assert.rejects(calcularRiesgo({ ...base, soqueado: true }, opciones), /meses_desde_zoca/);
  await assert.rejects(calcularRiesgo({ ...base, escenario: 'x' }, opciones), /escenario/);
});

test('esquema de entrada coherente', () => {
  assert.deepEqual(ESQUEMA_ENTRADA.required, ['lat', 'lon', 'edad_meses', 'soqueado', 'escenario']);
});
