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
    labSelect: createField(),
    aasIdInput: createField(),
    saveButton: createField(),
    checkButton: createField(),
    deleteButton: createField(),
    result: createField(),
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

test('saves an AAS link with the selected lab', async () => {
  const { fields, calls, toasts } = loadController({
    responses: [{ ok: true, status: 200, json: async () => ({ aasId: 'urn:linked' }) }],
  });
  fields.keyInput.value = 'spring damper.fmu';
  fields.labSelect.value = '7';
  fields.aasIdInput.value = 'urn:requested';

  fields.saveButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].url, '/aas-admin/fmu/spring%20damper.fmu/aas-link');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), { aasId: 'urn:requested', labId: '7' });
  assert.equal(fields.result.textContent, 'Linked: urn:linked');
  assert.deepEqual(toasts.at(-1), { message: 'AAS link saved for spring damper.fmu', type: 'success' });
  assert.equal(fields.saveButton.disabled, false);
});

test('loads an existing link and clears a missing link', async () => {
  const { fields, calls } = loadController({
    responses: [
      { ok: true, status: 200, json: async () => ({ aasId: 'urn:existing', labId: '42' }) },
      { ok: false, status: 404, json: async () => ({}) },
    ],
  });
  fields.keyInput.value = 'spring-damper.fmu';
  fields.aasIdInput.value = 'urn:stale';
  fields.labSelect.value = '7';

  fields.checkButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls[0].url, '/aas-admin/fmu/spring-damper.fmu/aas-link');
  assert.equal(fields.aasIdInput.value, 'urn:existing');
  assert.equal(fields.labSelect.value, '42');
  assert.equal(fields.checkButton.disabled, false);

  fields.checkButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fields.result.textContent, 'No link configured for this access key.');
  assert.equal(fields.aasIdInput.value, '');
});

test('deletes an AAS link and reports the result', async () => {
  const { fields, calls, toasts } = loadController({
    responses: [{ ok: true, status: 200, json: async () => ({}) }],
  });
  fields.keyInput.value = 'spring-damper.fmu';
  fields.aasIdInput.value = 'urn:existing';

  fields.deleteButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].options.method, 'DELETE');
  assert.equal(fields.result.textContent, 'Link removed.');
  assert.equal(fields.aasIdInput.value, '');
  assert.deepEqual(toasts.at(-1), { message: 'AAS link removed for spring-damper.fmu', type: 'success' });
  assert.equal(fields.deleteButton.disabled, false);
});