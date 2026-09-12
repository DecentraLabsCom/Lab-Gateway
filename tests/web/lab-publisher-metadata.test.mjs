import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const valuesScriptPath = new URL('web/assets/js/lab-publisher-values.js', repoRoot);
const metadataScriptPath = new URL('web/assets/js/lab-publisher-metadata.js', repoRoot);

function loadMetadata() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(valuesScriptPath, 'utf8'), context, {
    filename: 'lab-publisher-values.js',
  });
  vm.runInContext(fs.readFileSync(metadataScriptPath, 'utf8'), context, {
    filename: 'lab-publisher-metadata.js',
  });
  return context.window.LabPublisherMetadata;
}

function attributeMap(metadata) {
  return Object.fromEntries(metadata.attributes.map(attribute => [attribute.trait_type, attribute.value]));
}

test('builds slot metadata without changing the publisher serialization shape', () => {
  const metadata = loadMetadata().buildMetadata({
    contentId: 'lab-slot',
    name: 'Remote lab',
    description: 'A lab for testing',
    imageUrls: ['https://example.test/hero.png', 'https://example.test/second.png'],
    demoEnabled: true,
    classification: [{ scheme: 'OECD-FORD', code: '1.2', label: 'Computer sciences' }],
    keywords: ['physics', 'control'],
    resourceType: 'lab',
    fmuFileName: '',
    unavailableWindows: [{ startUnix: 10, endUnix: 20, reason: 'Maintenance' }],
    priceUnit: 'hour',
    rawPricePerSecond: 2778n,
    bookingMode: 'slot',
    timeSlots: [30, 60],
    allowedDurationRange: null,
    allowedDurations: [{ unit: 'minute', value: 30 }, { unit: 'minute', value: 60 }],
    periodRules: null,
    pricing: {
      displayAmount: '1',
      displayUnit: 'hour',
      rawPricePerSecond: '2778',
      roundingMode: 'nearest-per-second',
      billingMode: 'linear-duration',
    },
    termsOfUse: { url: 'https://example.test/terms' },
    availableDays: ['MONDAY'],
    availableHours: { start: '09:00', end: '17:00' },
    maxConcurrentUsers: 1,
    timezone: 'Europe/Madrid',
    fmiVersion: '',
    simulationType: '',
    modelVariables: [],
    defaultStartTime: '',
    defaultStopTime: '',
    defaultStepSize: '',
  });

  assert.equal(metadata.contentId, 'lab-slot');
  assert.equal(metadata.image, 'https://example.test/hero.png');
  assert.equal(metadata.demoEnabled, true);
  const attributes = attributeMap(metadata);
  assert.deepEqual(attributes.additionalImages, ['https://example.test/second.png']);
  assert.deepEqual(attributes.timeSlots, [30, 60]);
  assert.equal(attributes.bookingMode, 'slot');
  assert.equal(attributes.resourceType, 'lab');
  assert.equal(attributes.pricing.rawPricePerSecond, '2778');
  assert.equal(Object.hasOwn(attributes, 'allowedDurationRange'), false);
  assert.equal(Object.hasOwn(attributes, 'periodRules'), false);
  assert.equal(Object.hasOwn(attributes, 'fmiVersion'), false);
});

test('builds calendar-period FMU metadata with optional FMI attributes', () => {
  const metadata = loadMetadata().buildMetadata({
    contentId: 'lab-fmu',
    name: 'FMU lab',
    description: 'A simulation lab',
    imageUrls: [],
    demoEnabled: false,
    classification: [],
    keywords: [],
    resourceType: 'fmu',
    fmuFileName: 'model.fmu',
    unavailableWindows: [],
    priceUnit: 'day',
    rawPricePerSecond: 123n,
    bookingMode: 'calendar-period',
    timeSlots: [],
    allowedDurationRange: { unit: 'week', min: 1, max: 2 },
    allowedDurations: [{ unit: 'week', value: 1 }, { unit: 'week', value: 2 }],
    periodRules: { startGranularity: 'day', allowCustomDateRange: true, minDurationDays: 7, maxDurationDays: 14 },
    pricing: { displayAmount: '2', displayUnit: 'day', rawPricePerSecond: '123' },
    termsOfUse: {},
    availableDays: ['MONDAY', 'FRIDAY'],
    availableHours: {},
    maxConcurrentUsers: 2,
    timezone: 'UTC',
    fmiVersion: '3.0',
    simulationType: 'CoSimulation',
    modelVariables: [{ name: 'speed', type: 'Real' }],
    defaultStartTime: 0,
    defaultStopTime: 10,
    defaultStepSize: 0.1,
  });

  const attributes = attributeMap(metadata);
  assert.equal(metadata.image, '');
  assert.deepEqual(attributes.allowedDurationRange, { unit: 'week', min: 1, max: 2 });
  assert.deepEqual(attributes.periodRules, {
    startGranularity: 'day',
    allowCustomDateRange: true,
    minDurationDays: 7,
    maxDurationDays: 14,
  });
  assert.equal(attributes.fmuFileName, 'model.fmu');
  assert.equal(attributes.fmiVersion, '3.0');
  assert.equal(attributes.simulationType, 'CoSimulation');
  assert.deepEqual(attributes.modelVariables, [{ name: 'speed', type: 'Real' }]);
  assert.equal(attributes.defaultStartTime, 0);
  assert.equal(attributes.defaultStopTime, 10);
  assert.equal(attributes.defaultStepSize, 0.1);
  assert.equal(Object.hasOwn(attributes, 'timeSlots'), false);
});
