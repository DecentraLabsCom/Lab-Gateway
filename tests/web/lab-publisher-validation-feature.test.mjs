import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-validation-feature.js', repoRoot);

function createDocument(overrides = {}) {
  const ids = [
    'labResourceType',
    'labAccessURI',
    'labAccessKey',
    'labFmuFileName',
    'labTimezone',
    'labAvailableHoursStart',
    'labAvailableHoursEnd',
    'labTimeSlots',
    'labOpens',
    'labCloses',
  ];
  const elements = new Map(ids.map(id => [id, { value: overrides[id] ?? '' }]));
  return {
    getElementById: id => elements.get(id) || null,
  };
}

function loadFeature({ documentImpl, contentState = {}, pricingState = {}, availabilityState = {}, bookingMode = 'slot' }) {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const context = vm.createContext({ window: {}, document: documentImpl, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-validation-feature.js' });
  return context.window.LabPublisherValidationFeature.createController({
    documentImpl,
    getContentState: () => contentState,
    getPricingState: () => pricingState,
    getAvailabilityState: () => availabilityState,
    getBookingMode: () => bookingMode,
    getAllowedPeriodRange: () => ({ unit: 'day', min: 1, max: 2 }),
    getFordField: code => code === '1.2' ? { code } : null,
    expandAllowedDurations: range => range?.min ? [{ unit: range.unit, value: range.min }] : [],
    splitCsv: value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
    dateInputToUnix: value => value ? 1 : 0,
  });
}

function validOptions(overrides = {}) {
  const documentImpl = createDocument({
    labResourceType: '0',
    labAccessURI: 'https://gateway.example/guacamole',
    labAccessKey: 'guac:id:42',
    labTimezone: 'Europe/Madrid',
    labAvailableHoursStart: '09:00',
    labAvailableHoursEnd: '17:00',
    labTimeSlots: '30,60',
    labOpens: '2026-01-01',
    labCloses: '2026-12-31',
    ...overrides,
  });
  return {
    documentImpl,
    contentState: { name: 'Lab', description: 'Description' },
    pricingState: { displayAmount: '1' },
    availabilityState: { selectedCategories: ['1.2'], availableDays: ['MONDAY'] },
    bookingMode: 'slot',
  };
}

test('preserves required metadata, schedule and access validation', () => {
  const options = validOptions({ labAccessKey: '' });
  const controller = loadFeature(options);

  assert.throws(() => controller.validate(), /Connection ID is required/);
  options.documentImpl.getElementById('labAccessKey').value = 'guac:id:42';
  assert.doesNotThrow(() => controller.validate());

  options.documentImpl.getElementById('labOpens').value = '';
  assert.throws(() => controller.validate(), /Opens is required/);
});

test('preserves calendar-period and FMU-specific guards', () => {
  const calendarOptions = validOptions({ labResourceType: '0' });
  const calendarController = loadFeature({ ...calendarOptions, bookingMode: 'calendar-period' });
  assert.doesNotThrow(() => calendarController.validate());

  const fmuOptions = validOptions({
    labResourceType: '1',
    labAccessKey: 'model.fmu',
    labFmuFileName: 'model.txt',
  });
  const fmuController = loadFeature(fmuOptions);
  assert.throws(() => fmuController.validate(), /must end with \.fmu/);
  fmuOptions.documentImpl.getElementById('labFmuFileName').value = 'model.fmu';
  assert.doesNotThrow(() => fmuController.validate());
});
