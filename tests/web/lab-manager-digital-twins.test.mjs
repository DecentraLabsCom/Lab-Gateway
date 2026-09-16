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
    dataset: {},
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
    aasLinkKey: createElement('aasLinkKey'),
    aasx: {
      packageList: createElement('aasxPackageList'),
    },
  };
  fields.fmuSync = {};
  fields.aasLink = {};
  return fields;
}

function loadDigitalTwins({
  labsResponse,
  associationsResponse = {
    ok: true,
    status: 200,
    json: async () => ({ associations: [] }),
  },
}) {
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
  const aasxCalls = [];
  const aasxModule = {
    createController: (options) => {
      aasxCalls.push(options);
      return {
        initialize: () => aasxCalls.push('initialize'),
        setManagedLabs: () => {},
        loadPackages: async () => true,
        clearPackages: () => {},
      };
    },
  };
  const fetchCalls = [];
  const context = vm.createContext({
    document,
    window: {
      LabManagerFmuSync: fmuSyncModule,
      LabManagerAasLink: aasLinkModule,
      LabManagerAasx: aasxModule,
    },
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
    return Promise.resolve(
      String(url) === '/ops/api/lab-associations' ? associationsResponse : labsResponse,
    );
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
    aasxModule,
  });
  return { controller, fields, fetchCalls, fmuCalls, aasCalls, aasxCalls };
}

test('loads managed labs once and populates both digital-twin selectors by stable lab ID', async () => {
  const { controller, fields, fetchCalls } = loadDigitalTwins({
    labsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          {
            labId: '7',
            resourceType: 1,
            accessKey: 'spring.fmu',
            name: 'Spring Damper',
            description: 'Registered spring damper laboratory',
            documentation: [
              'https://docs.example.test/manual.pdf',
              'https://docs.example.test/guide.html',
            ],
            termsOfUse: { url: 'https://docs.example.test/terms.html' },
            listed: true,
          },
          {
            labId: '8',
            resourceType: 0,
            accessKey: 'guac:id:8',
            name: 'Remote Station',
            listed: false,
          },
        ],
      }),
    },
    associationsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        associations: [{ labId: '8', hostName: 'PC-Siemens' }],
      }),
    },
  });

  fields.powerPolicyLabSelect.value = '8';
  fields.fmuSyncKey.value = '7';
  fields.aasLinkKey.value = '7';
  const first = controller.loadManagedLabsOnce({ skipAuthPrompt: true });
  const second = controller.loadManagedLabsOnce({ skipAuthPrompt: false });
  assert.equal(first, second);
  await first;

  assert.equal(fetchCalls.length, 2);
  assert.equal(fetchCalls[0].url, '/lab-admin/labs');
  assert.equal(fetchCalls[1].url, '/ops/api/lab-associations');
  assert.equal(fetchCalls[0].options.skipAuthPrompt, true);
  assert.equal(controller.getManagedLabs().length, 2);
  assert.equal(fields.powerPolicyLabSelect.value, '8');
  assert.equal(fields.fmuSyncKey.value, '7');
  assert.equal(fields.aasLinkKey.value, '7');
  assert.deepEqual(fields.fmuSyncKey.options.map(option => option.value), ['7', '8']);
  assert.equal(
    fields.fmuSyncKey.options.find(option => option.value === '7').dataset.labId,
    '7',
  );
  assert.equal(
    fields.aasLinkKey.options.find(option => option.value === '7').dataset.labId,
    '7',
  );
  assert.equal(
    fields.fmuSyncKey.options.find(option => option.value === '7').dataset.labDescription,
    'Registered spring damper laboratory',
  );
  assert.deepEqual(
    JSON.parse(fields.fmuSyncKey.options.find(option => option.value === '7').dataset.labDocumentation),
    ['https://docs.example.test/manual.pdf', 'https://docs.example.test/guide.html'],
  );
  assert.equal(
    fields.fmuSyncKey.options.find(option => option.value === '7').dataset.labLicense,
    'https://docs.example.test/terms.html',
  );
  assert.equal(
    fields.fmuSyncKey.options.find(option => option.value === '8').dataset.resourceType,
    '0',
  );
  assert.ok(fields.powerPolicyLabSelect.options.some(option => /Spring Damper/.test(option.textContent)));
});

test('only exposes physical laboratories reported by the Ops Worker association projection', async () => {
  const { controller, fields } = loadDigitalTwins({
    labsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '1', resourceType: 1, accessKey: 'state-space.fmu', name: 'State Space' },
          {
            labId: '2',
            resourceType: 0,
            accessKey: 'guac:id:21',
            name: 'Associated physical lab',
          },
          {
            labId: '3',
            resourceType: 0,
            accessKey: 'guac:id:22',
            name: 'Unassociated physical lab',
          },
        ],
      }),
    },
    associationsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        associations: [{ labId: '2', hostName: 'PC-Siemens' }],
      }),
    },
  });

  await controller.loadManagedLabs({ skipAuthPrompt: true });

  assert.deepEqual(fields.fmuSyncKey.options.map(option => option.value), ['1', '2']);
  assert.deepEqual(fields.aasLinkKey.options.map(option => option.value), ['1', '2']);
  assert.equal(controller.getManagedLabs().length, 3);
});

test('hides physical laboratories when the Ops Worker associations cannot be loaded', async () => {
  const { controller, fields } = loadDigitalTwins({
    labsResponse: {
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '1', resourceType: 1, accessKey: 'state-space.fmu', name: 'State Space' },
          { labId: '2', resourceType: 0, accessKey: 'guac:id:2', name: 'Physical lab' },
        ],
      }),
    },
    associationsResponse: {
      ok: false,
      status: 503,
      json: async () => ({}),
    },
  });

  await controller.loadManagedLabs({ skipAuthPrompt: true });

  assert.deepEqual(fields.fmuSyncKey.options.map(option => option.value), ['1']);
  assert.deepEqual(fields.aasLinkKey.options.map(option => option.value), ['1']);
});

test('initializes FMU sync, AAS link and AASX catalog with their field boundaries', () => {
  const { controller, fields, fmuCalls, aasCalls, aasxCalls } = loadDigitalTwins({
    labsResponse: { ok: true, status: 200, json: async () => ({ labs: [] }) },
  });

  controller.initialize();
  assert.equal(fmuCalls.length, 2);
  assert.equal(aasCalls.length, 2);
  assert.equal(fmuCalls[0].fields, fields.fmuSync);
  assert.equal(aasCalls[0].fields, fields.aasLink);
  assert.equal(aasxCalls[0].fields, fields.aasx);
  assert.equal(aasxCalls[0].resolveLabDisplayName({ labId: '11' }), 'Lab #11');
});

test('resolves managed lab names with stable id fallbacks', () => {
  const { controller } = loadDigitalTwins({
    labsResponse: { ok: true, status: 200, json: async () => ({ labs: [] }) },
  });

  assert.equal(controller.resolveLabDisplayName({ metadata: { name: 'Metadata name' }, labId: '9' }), 'Metadata name');
  assert.equal(controller.resolveLabDisplayName({ labId: '10' }), 'Lab #10');
});
