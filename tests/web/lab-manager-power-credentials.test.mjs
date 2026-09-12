import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-credentials.js', repoRoot);

function createElement() {
  return {
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    textContent: '',
    innerHTML: '',
    options: [],
    addEventListener() {},
    appendChild(option) {
      this.options.push(option);
    },
  };
}

function loadController({ fetchImpl = async () => ({
  ok: true,
  status: 200,
  json: async () => ({ credentials: [] }),
}), credential = null } = {}) {
  const fields = {
    select: createElement(),
    ref: createElement(),
    type: createElement(),
    username: createElement(),
    password: createElement(),
    community: createElement(),
    authProtocol: createElement(),
    authPassword: createElement(),
    privProtocol: createElement(),
    privPassword: createElement(),
    contextName: createElement(),
    usernameField: createElement(),
    passwordField: createElement(),
    communityField: createElement(),
    authProtocolField: createElement(),
    authPasswordField: createElement(),
    privProtocolField: createElement(),
    privPasswordField: createElement(),
    contextNameField: createElement(),
    saveButton: createElement(),
    list: createElement(),
    status: createElement(),
    hint: createElement(),
    editorHint: createElement(),
  };
  fields.type.value = 'netio-http-basic';
  fields.authProtocol.value = 'NONE';
  fields.privProtocol.value = 'NONE';
  const toasts = [];
  const controllerStatuses = [];
  const context = vm.createContext({
    console,
    document: {
      createElement: () => ({ value: '', textContent: '' }),
    },
    window: {},
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: path.basename(scriptPath.pathname),
  });
  const controller = context.window.LabManagerPowerCredentials.createController({
    fields,
    fetchImpl,
    showToast: (message, type) => toasts.push({ message, type }),
    showOpsWarning: () => toasts.push({ message: 'ops-warning', type: 'warning' }),
    refreshPowerControllerStatuses: (options) => controllerStatuses.push(options),
  });
  controller.initialize();
  if (credential) controller.populateForm(credential);
  return { controller, fields, toasts, controllerStatuses };
}

test('shows only credential fields relevant to the selected type', () => {
  const { controller, fields } = loadController();

  controller.updateFields();
  assert.equal(fields.usernameField.hidden, false);
  assert.equal(fields.passwordField.hidden, false);
  assert.equal(fields.communityField.hidden, true);
  assert.equal(fields.authProtocolField.hidden, true);

  fields.type.value = 'snmpv3';
  fields.authProtocol.value = 'SHA256';
  fields.privProtocol.value = 'AES';
  controller.updateFields();
  assert.equal(fields.usernameField.hidden, false);
  assert.equal(fields.passwordField.hidden, true);
  assert.equal(fields.communityField.hidden, true);
  assert.equal(fields.authProtocolField.hidden, false);
  assert.equal(fields.authPasswordField.hidden, false);
  assert.equal(fields.privProtocolField.hidden, false);
  assert.equal(fields.privPasswordField.hidden, false);
  assert.equal(fields.contextNameField.hidden, false);

  fields.type.value = 'snmpv2c';
  controller.updateFields();
  assert.equal(fields.usernameField.hidden, true);
  assert.equal(fields.communityField.hidden, false);
});

test('saves a NETIO credential without leaking unrelated fields', async () => {
  const calls = [];
  const { controller, fields } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ credentials: [] }) };
    },
  });
  fields.ref.value = 'netio-lab-01-http';
  fields.username.value = 'netio-api';
  fields.password.value = 'secret-from-form';

  await controller.save();

  assert.equal(calls[0].url, '/ops/api/power/credentials');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    credentialRef: 'netio-lab-01-http',
    type: 'netio-http-basic',
    credentials: { username: 'netio-api', password: 'secret-from-form' },
    overwrite: false,
  });
  assert.equal(fields.password.value, '');
});

test('loads an existing credential and rotates it with overwrite', async () => {
  const { controller, fields, controllerStatuses } = loadController({
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ credentials: [{ credentialRef: 'existing', type: 'netio-http-basic' }] }),
    }),
  });

  await controller.load();
  fields.select.value = 'existing';
  controller.loadSelected();
  assert.equal(fields.ref.value, 'existing');
  assert.equal(fields.ref.disabled, true);
  assert.equal(fields.password.value, '');
  fields.username.value = 'replacement-user';
  fields.password.value = 'replacement-secret';
  await controller.save();

  assert.equal(controllerStatuses.length, 1);
  assert.equal(controllerStatuses[0].forceRefresh, true);
});
