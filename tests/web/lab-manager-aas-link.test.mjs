import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-aas-link.js', repoRoot);

function createField(value = '') {
  const listeners = new Map();
  return {
    disabled: false,
    style: { color: '' },
    textContent: '',
    value,
    options: [],
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    dispatchEvent(event) {
      return listeners.get(event.type)?.(event);
    },
  };
}

function loadController({ responses = [] } = {}) {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-aas-link.js',
  });

  const fields = {
    keyInput: createField(),
    aasIdInput: createField(),
    saveButton: createField(),
    checkButton: createField(),
    deleteButton: createField(),
  };
  const calls = [];
  const toasts = [];
  const controller = context.window.LabManagerAasLink.createController({
    fields,
    fetchImpl: async (url, options = {}) => {
      calls.push({ url: String(url), options });
      return responses.shift() || { ok: true, status: 200, json: async () => ({}) };
    },
    showToast: (message, type) => toasts.push({ message, type }),
    encodeURIComponentImpl: encodeURIComponent,
  });
  controller.initialize();
  return { fields, calls, toasts };
}

test('saves an AAS link by stable lab ID', async () => {
  const { fields, calls, toasts } = loadController({
    responses: [{ ok: true, status: 200, json: async () => ({ aasId: 'urn:linked' }) }],
  });
  fields.keyInput.value = '7';
  fields.keyInput.options = [{ value: '7', dataset: { labId: '7', resourceType: '0' } }];
  fields.aasIdInput.value = 'urn:requested';

  fields.saveButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].url, '/aas-admin/lab/7/aas-link');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), { aasId: 'urn:requested' });
  assert.deepEqual(toasts.at(-1), { message: 'AAS link saved for laboratory 7', type: 'success' });
  assert.equal(fields.saveButton.disabled, false);
});

test('loads an existing link and reports a missing link through the toast', async () => {
  const { fields, calls, toasts } = loadController({
    responses: [
      { ok: true, status: 200, json: async () => ({ aasId: 'urn:existing', labId: '42' }) },
      { ok: false, status: 404, json: async () => ({}) },
    ],
  });
  fields.keyInput.value = '7';
  fields.aasIdInput.value = 'urn:stale';
  fields.keyInput.options = [{ value: '7', dataset: { labId: '7' } }];

  fields.checkButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls[0].url, '/aas-admin/lab/7/aas-link');
  assert.equal(fields.aasIdInput.value, 'urn:existing');
  assert.deepEqual(toasts.at(-1), {
    message: 'AAS link checked for laboratory 7: urn:existing',
    type: 'success',
  });
  assert.equal(fields.keyInput.value, '7');
  assert.equal(fields.checkButton.disabled, false);

  fields.checkButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fields.aasIdInput.value, '');
  assert.deepEqual(toasts.at(-1), {
    message: 'No AAS link configured for laboratory 7',
    type: 'info',
  });
});

test('deletes an AAS link and reports it through the toast', async () => {
  const { fields, calls, toasts } = loadController({
    responses: [{ ok: true, status: 200, json: async () => ({}) }],
  });
  fields.keyInput.value = '7';
  fields.aasIdInput.value = 'urn:existing';

  fields.deleteButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].options.method, 'DELETE');
  assert.equal(fields.aasIdInput.value, '');
  assert.deepEqual(toasts.at(-1), { message: 'AAS link removed for laboratory 7', type: 'success' });
  assert.equal(fields.deleteButton.disabled, false);
});

test('reports AAS link check failures through the toast', async () => {
  const { fields, toasts } = loadController({
    responses: [{ ok: false, status: 503, json: async () => ({}) }],
  });
  fields.keyInput.value = '7';

  fields.checkButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(toasts.at(-1), {
    message: 'AAS link check failed: HTTP 503',
    type: 'error',
  });
});
