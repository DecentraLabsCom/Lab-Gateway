import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-controllers.js', repoRoot);

function createField(value = '') {
  return {
    value,
    checked: false,
    hidden: false,
    disabled: false,
    dataset: {},
    children: [],
    innerHTML: '',
    addEventListener() {},
    appendChild(child) { this.children.push(child); },
  };
}

function loadControllers(overrides = {}) {
  const context = vm.createContext({ console, window: { crypto: { randomUUID: () => 'test-key' } } });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-controllers.js',
  });
  const fields = {
    id: createField('netio-main'),
    name: createField('Main NETIO'),
    driver: createField('netio-json'),
    enabled: createField(),
    host: createField('pdu.example.test'),
    port: createField('443'),
    credentialRef: createField(''),
    netioPath: createField('/netio.json'),
    netioHttps: createField(),
    netioVerifyTls: createField(),
    profile: createField('auto'),
    timeoutSeconds: createField('2'),
    retries: createField('1'),
    outlets: createField(),
    list: createField(),
    select: createField(),
    status: createField(),
    hint: createField(),
    editorHint: createField(),
    saveButton: createField(),
    operationReason: createField(),
    cycleSeconds: createField('10'),
    maintenanceMode: createField(),
  };
  const toasts = [];
  const controller = context.window.LabManagerPowerControllers.createController({
    fields,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    showToast: (message, type) => toasts.push({ message, type }),
    showOpsWarning() {},
    renderControllerRowsMarkup: () => [],
    renderControllerCredentialOptionsMarkup: () => '',
    renderControllerOutletsMarkup: () => '',
    mergePowerControllerStatuses: (controllers) => controllers,
    createPowerControllerOutletDraft: overrides.createPowerControllerOutletDraft || ((outlet = {}) => ({ outlet: outlet.outlet || '' })),
    buildPowerCommandPayload: () => ({}),
    documentImpl: { createElement: () => createField() },
    ...overrides,
  });
  return { controller, fields, toasts };
}

test('preserves controller form validation and NETIO payload shape', () => {
  const { controller, fields } = loadControllers({
    createPowerControllerOutletDraft: outlet => ({
      outlet: String(outlet.outlet || ''),
      logicalName: '',
      protected: false,
      defaultState: 'off',
    }),
  });
  controller.resetEditor();
  fields.id.value = 'netio-main';
  fields.name.value = 'Main NETIO';
  fields.driver.value = 'netio-json';
  fields.host.value = 'pdu.example.test';
  fields.port.value = '443';
  fields.netioHttps.checked = true;

  assert.deepEqual(JSON.parse(JSON.stringify(controller.readForm())), {
    id: 'netio-main',
    name: 'Main NETIO',
    driver: 'netio-json',
    enabled: true,
    host: 'pdu.example.test',
    port: 443,
    credentialRef: '',
    config: {
      path: '/netio.json',
      useHttps: true,
      verifyTls: true,
      timeoutSeconds: 2,
      retries: 1,
    },
    outlets: [{
      outlet: '1',
      logicalName: '',
      protected: false,
      defaultState: 'off',
    }],
  });
  fields.id.value = 'invalid id';
  assert.throws(() => controller.readForm(), { message: 'Controller ID contains invalid characters' });
});

test('keeps driver port suggestions and controller ID suggestions stable', () => {
  const { controller, fields } = loadControllers({
    createPowerControllerOutletDraft: outlet => ({ outlet: String(outlet.outlet || '') }),
  });
  controller.resetEditor();
  fields.driver.value = 'mock';
  fields.port.value = '161';
  fields.host.value = 'Station A / PDU';
  controller.updateDriverFields();
  controller.suggestId();
  assert.equal(fields.id.value, 'power-station-a-pdu');
  fields.driver.value = 'netio-json';
  controller.updateDriverFields();
  assert.equal(fields.port.value, '80');
  controller.suggestId();
  assert.equal(fields.id.value, 'netio-station-a-pdu');
});

test('preserves controller load status and authorization request behavior', async () => {
  const calls = [];
  const responses = [
    { ok: true, status: 200, json: async () => ({ controllers: [{ id: 'pdu-1', name: 'Main', outlets: [] }] }) },
    { ok: true, status: 200, json: async () => ({ controllers: [{ id: 'pdu-1', discovery: { reachable: true }, outlets: [] }] }) },
  ];
  const { controller } = loadControllers({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return responses.shift();
    },
  });
  await controller.load({ skipAuthPrompt: true, forceStatusRefresh: true });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls[0].url, '/ops/api/power/controllers');
  assert.equal(calls[0].options.cache, 'no-store');
  assert.equal(calls[1].url, '/ops/api/power/controllers/status?refresh=true');
  assert.equal(calls[1].options.cache, 'no-store');
});

test('reports a successful explicit controller refresh', async () => {
  const { controller, toasts } = loadControllers();

  await controller.load({ notifySuccess: true });

  assert.deepEqual(toasts, [{ message: 'Power controllers refreshed', type: 'success' }]);
});

test('reports access denial on an explicit controller refresh', async () => {
  const { controller, toasts } = loadControllers({
    fetchImpl: async () => ({ ok: false, status: 403, json: async () => ({}) }),
  });

  await controller.load({ notifyError: true });

  assert.deepEqual(toasts, [{
    message: 'Access denied: /ops blocked by Lab Manager access policy',
    type: 'error',
  }]);
});

test('sends the unified physical output name and keeps the local name aligned', () => {
  const { controller, fields } = loadControllers({
    createPowerControllerOutletDraft: outlet => ({
      outlet: String(outlet.outlet || ''),
      deviceName: outlet.deviceName || '',
      deviceConfig: { ...(outlet.deviceConfig || {}) },
      deviceConfigFields: outlet.deviceConfigFields || ['name', 'powerOnDelaySeconds'],
      deviceConfigWritable: true,
      deviceManaged: true,
      logicalName: '',
      protected: false,
      defaultState: 'off',
    }),
  });
  controller.populateForm({
    id: 'apc-1',
    name: 'APC',
    driver: 'apc-powernet-snmp',
    host: '192.0.2.20',
    port: 161,
    credentialRef: 'apc-1',
    config: { profile: 'legacy' },
    outlets: [{
      outlet: '1',
      deviceName: 'PLC',
      deviceConfig: { powerOnDelaySeconds: 0 },
      deviceConfigFields: ['name', 'powerOnDelaySeconds'],
      deviceConfigWritable: true,
      logicalName: 'plc',
    }],
  });
  const target = {
    type: 'text',
    value: 'PLC updated',
    dataset: { controllerOutletField: 'deviceName' },
    closest: () => ({ dataset: { controllerOutletIndex: '0' } }),
  };
  controller.handleOutletChange({ target });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.readForm().deviceConfiguration)), {
    outlets: [{ outlet: '1', name: 'PLC updated', config: { powerOnDelaySeconds: 0 } }],
  });
  assert.deepEqual(JSON.parse(JSON.stringify(controller.readForm().outlets)), [{
    outlet: '1',
    logicalName: 'PLC updated',
    protected: false,
    defaultState: 'off',
  }]);

  controller.handleOutletChange({
    target: {
      type: 'text',
      value: 'x'.repeat(21),
      dataset: { controllerOutletField: 'deviceName' },
      closest: () => ({ dataset: { controllerOutletIndex: '0' } }),
    },
  });
  assert.throws(() => controller.readForm(), { message: 'Output 1: device name is too long' });
});
