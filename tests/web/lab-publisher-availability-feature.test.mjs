import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-availability-feature.js', repoRoot);

function createElement(id) {
  const listeners = [];
  return {
    id,
    value: '',
    checked: false,
    hidden: false,
    innerHTML: '',
    textContent: '',
    classList: {
      contains: () => false,
      toggle() {},
      add() {},
      remove() {},
    },
    style: {},
    addEventListener(type, listener) {
      listeners.push({ type, listener });
    },
    querySelectorAll: () => [],
    setAttribute() {},
    getBoundingClientRect: () => ({ left: 0, bottom: 0 }),
    listeners,
  };
}

function loadFeature() {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map([
    'labCategorySelect', 'labCategoryMenu', 'labCategoryChips',
    'labEducationalProgramLinked', 'labIscedSuggestions', 'labAvailableDays',
    'labAddUnavailableWindow', 'labUnavailableWindows',
  ].map(id => [id, createElement(id)]));
  const document = {
    getElementById: id => elements.get(id) || null,
    addEventListener() {},
  };
  const context = vm.createContext({ window: {}, document, console, Date });
  vm.runInContext(source, context, { filename: 'lab-publisher-availability-feature.js' });
  const controller = context.window.LabPublisherAvailabilityFeature.createController({
    documentImpl: document,
    fordFieldsGrouped: { '1 Natural Sciences': [{ code: '1.2', label: 'Computer sciences' }] },
    iscedFields: [{ code: '061', label: 'Information and Communication Technologies' }],
    getSuggestedIscedCodes: () => ['061'],
    weekdayOptions: [
      { value: 'MONDAY', label: 'Mon' },
      { value: 'TUESDAY', label: 'Tue' },
    ],
    escapeHtml: value => String(value ?? ''),
    escapeAttr: value => String(value ?? ''),
    createClientId: () => 'window-1',
    toDatetimeLocal: value => value ? `date-${value}` : '',
    dateCtor: Date,
  });
  return { controller, elements };
}

test('owns classification and availability state while preserving its rendering boundary', () => {
  const { controller, elements } = loadFeature();

  controller.initialize();
  controller.hydrate({
    selectedCategories: ['1.2'],
    selectedIscedCodes: ['061'],
    iscedSelectionTouched: true,
    educationalProgramLinked: true,
    availableDays: ['MONDAY'],
    unavailableWindows: [{ startUnix: 10, endUnix: 20, reason: 'Maintenance' }],
  });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    selectedCategories: ['1.2'],
    selectedIscedCodes: ['061'],
    iscedSelectionTouched: true,
    educationalProgramLinked: true,
    availableDays: ['MONDAY'],
    unavailableWindows: [{ startUnix: 10, endUnix: 20, reason: 'Maintenance', clientId: 'window-1' }],
  });
  assert.match(elements.get('labCategoryChips').innerHTML, /Computer sciences/);
  assert.match(elements.get('labIscedSuggestions').innerHTML, /Information and Communication Technologies/);
  assert.match(elements.get('labAvailableDays').innerHTML, /data-day="MONDAY"/);
  assert.match(elements.get('labUnavailableWindows').innerHTML, /Maintenance/);
});
