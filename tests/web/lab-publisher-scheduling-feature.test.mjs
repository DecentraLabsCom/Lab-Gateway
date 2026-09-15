import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-scheduling-feature.js', repoRoot);

function createElement({ id = '', className = '' } = {}) {
  const classes = new Set(className.split(/\s+/).filter(Boolean));
  const listeners = new Map();
  return {
    id,
    value: '',
    _innerHTML: '',
    get innerHTML() {
      return this._innerHTML;
    },
    set innerHTML(value) {
      this._innerHTML = String(value);
      this.children.length = 0;
    },
    children: [],
    min: '',
    max: '',
    step: '',
    classList: {
      contains: name => classes.has(name),
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
    },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    dispatch(type) {
      listeners.get(type)?.({ target: this });
    },
    add(option) {
      this.children.push(option);
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    listeners,
  };
}

function loadFeature() {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map([
    ['labPriceUnit', createElement({ id: 'labPriceUnit' })],
    ['labBookingMode', createElement({ id: 'labBookingMode' })],
    ['labAllowedPeriodMin', createElement({ id: 'labAllowedPeriodMin' })],
    ['labAllowedPeriodMax', createElement({ id: 'labAllowedPeriodMax' })],
    ['labAllowedPeriodUnit', createElement({ id: 'labAllowedPeriodUnit' })],
    ['labTimezone', createElement({ id: 'labTimezone' })],
  ]);
  const grids = [createElement({ className: 'scheduling-grid' })];
  const slotFields = [createElement({ className: 'booking-slot-field' })];
  const periodFields = [createElement({ className: 'booking-period-field' })];
  const document = {
    getElementById: id => elements.get(id) || null,
    querySelectorAll(selector) {
      if (selector === '.scheduling-grid') return grids;
      if (selector === '.booking-slot-field') return slotFields;
      if (selector === '.booking-period-field') return periodFields;
      return [];
    },
    createElement: () => createElement(),
  };
  const context = vm.createContext({ window: {}, document, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-scheduling-feature.js' });
  const controller = context.window.LabPublisherSchedulingFeature.createController({
    documentImpl: document,
    normalizePricingUnit: value => ['hour', 'day', 'week', 'month'].includes(value) ? value : 'hour',
    normalizePeriodUnit: value => ['day', 'week', 'month'].includes(value) ? value : 'day',
    resolveSupportedTimezones: () => ['Europe/Madrid', 'UTC'],
    resolveBrowserTimezone: () => 'UTC',
  });
  return { controller, document, elements, grids, slotFields, periodFields };
}

test('owns booking mode, period controls and timezone initialization', () => {
  const { controller, elements, grids, slotFields, periodFields } = loadFeature();
  const priceUnit = elements.get('labPriceUnit');
  const periodMin = elements.get('labAllowedPeriodMin');
  const periodMax = elements.get('labAllowedPeriodMax');
  const periodUnit = elements.get('labAllowedPeriodUnit');
  const bookingMode = elements.get('labBookingMode');
  const timezone = elements.get('labTimezone');

  priceUnit.value = 'hour';
  controller.initialize();

  assert.equal(bookingMode.value, 'slot');
  assert.equal(slotFields[0].classList.contains('is-hidden'), false);
  assert.equal(periodFields[0].classList.contains('is-hidden'), true);
  assert.equal(grids[0].classList.contains('calendar-period-mode'), false);
  assert.equal(periodMin.value, '1');
  assert.equal(periodMax.value, '1');
  assert.deepEqual(timezone.children.map(option => option.value), ['Europe/Madrid', 'UTC']);
  assert.equal(timezone.value, 'UTC');

  priceUnit.value = 'week';
  priceUnit.dispatch('change');

  assert.equal(bookingMode.value, 'calendar-period');
  assert.equal(slotFields[0].classList.contains('is-hidden'), true);
  assert.equal(periodFields[0].classList.contains('is-hidden'), false);
  assert.equal(grids[0].classList.contains('calendar-period-mode'), true);
  assert.deepEqual(elements.get('labAllowedPeriodUnit').children.map(option => option.value), ['week', 'month']);
  assert.equal(periodUnit.value, 'week');
  assert.equal(periodMax.max, '12');
});

test('normalizes and reads calendar-period ranges through the public API', () => {
  const { controller, elements } = loadFeature();
  const periodMin = elements.get('labAllowedPeriodMin');
  const periodMax = elements.get('labAllowedPeriodMax');
  const periodUnit = elements.get('labAllowedPeriodUnit');

  controller.initialize();
  controller.setAllowedPeriodRangeControls({ unit: 'month', min: 2, max: 9 });

  assert.equal(periodUnit.value, 'month');
  assert.equal(periodMin.value, '2');
  assert.equal(periodMax.value, '3');
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getSelectedAllowedPeriodRange())), {
    unit: 'month',
    min: 2,
    max: 3,
  });

  periodMin.value = '0';
  periodMax.value = '99';
  controller.normalizeAllowedPeriodRange();
  assert.equal(periodMin.value, '1');
  assert.equal(periodMax.value, '3');
});
