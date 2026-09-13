import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-digital-twins.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  const element = {
    id,
    value: '',
    disabled: false,
    innerHTML: '',
    options: [],
    addEventListener: (type, handler) => listeners.set(type, handler),
    appendChild: (child) => {
      element.options.push(child);
      return child;
    },
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
  };
  return element;
}

function createFields() {
  const fields = {
    powerPolicyLabSelect: createElement('powerPolicyLabSelect'),
    powerPolicySelect: createElement('powerPolicySelect'),
    fmuSyncKey: createElement('fmuSyncKey'),
    fmuSyncLabSelect: createElement('fmuSyncLabSelect'),
    aasLinkLabSelect: createElement('aasLinkLabSelect'),
  };
  fields.fmuSync = {};
  fields.aasLink = {};
  return fields;
}

function loadDigitalTwins({ labsResponse }) {
  const document = {
    createElement: (tagName) => {
      const element = createElement(tagName);
      element.options = [];
      element.appendChild = (child) => {
        element.options.push(child);
        return child;
      };
      return element;
    },
  };
  const fmuCalls = [];
  const aasCalls = [];
  const fmuSyncModule = {
    createController: (options) => {
      fmuCalls.push(options);
      return { initialize: () => fmuCalls.push('initialize') };
    },
  };
  const aasLinkModule = {
    createController: (options) => {
      aasCalls.push(options);
      return { initialize: () => aasCalls.push('initialize') };
    },
  };
  const fetchCalls = [];
  const context = vm.createContext({
    document,
    window: { LabManagerFmuSync: fmuSyncModule, LabManagerAasLink: aasLinkModule },
    console,
    Intl,
    Promise,
    setTimeout,
    clearTimeout,
    Option: function Option(text, value) {
      this.textContent = text;
      this.value = value;
    },
  });
  const fetchImpl = (url, options = {}) => {
    fetchCalls.push({ url: String(url), options });
    return Promise.resolve(labsResponse);
  };
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-digital-twins.js',
  });
  const fields = createFields();
  const controller = context.window.LabManagerDigitalTwins.createController({
    fields,
    fetchImpl,
    showToast: () => {},
    showOpsWarning: () => {},
    documentImpl: document,
    fmuSyncModule,
    aasLinkModule,
  });
  return { controller, fields, fetchCalls, fmuCalls, aasCalls };
}

test('loads managed labs once and preserves FMU and policy selector options', async () => {
  const { controller, fields, fetchCalls } = loadDigitalTwins({
    labsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '7', resourceType: 1, accessKey: 'spring.fmu', metadata: { name: 'Spring Damper' }, listed: true },
          { labId: '8', resourceType: 2, name: 'Remote Station', listed: false },
        ],
      }),
    },
  });

  fields.powerPolicyLabSelect.value = '8';
  fields.fmuSyncKey.value = 'spring.fmu';
  fields.fmuSyncLabSelect.value = '7';
  fields.aasLinkLabSelect.value = '7';
  const first = controller.loadManagedLabsOnce({ skipAuthPrompt: true });
  const second = controller.loadManagedLabsOnce({ skipAuthPrompt: false });
  assert.equal(first, second);
  await first;

  assert.equal(fetchCalls.length, 1);
  assert.equal(fetchCalls[0].url, '/lab-admin/labs');
  assert.equal(fetchCalls[0].options.skipAuthPrompt, true);
  assert.equal(controller.getManagedLabs().length, 2);
  assert.equal(fields.powerPolicyLabSelect.value, '8');
  assert.equal(fields.fmuSyncKey.value, 'spring.fmu');
  assert.equal(fields.fmuSyncLabSelect.value, '7');
  assert.equal(fields.aasLinkLabSelect.value, '7');
  assert.ok(fields.powerPolicyLabSelect.options.some(option => /Spring Damper/.test(option.textContent)));
});

test('initializes FMU sync and AAS link with the existing field boundaries', () => {
  const { controller, fields, fmuCalls, aasCalls } = loadDigitalTwins({
    labsResponse: { ok: true, status: 200, json: async () => ({ labs: [] }) },
  });

  controller.initialize();
  assert.equal(fmuCalls.length, 2);
  assert.equal(aasCalls.length, 2);
  assert.equal(fmuCalls[0].fields, fields.fmuSync);
  assert.equal(aasCalls[0].fields, fields.aasLink);
});

test('resolves managed lab names with stable id fallbacks', () => {
  const { controller } = loadDigitalTwins({
    labsResponse: { ok: true, status: 200, json: async () => ({ labs: [] }) },
  });

  assert.equal(controller.resolveLabDisplayName({ metadata: { name: 'Metadata name' }, labId: '9' }), 'Metadata name');
  assert.equal(controller.resolveLabDisplayName({ labId: '10' }), 'Lab #10');
});
