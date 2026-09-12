import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-fmu-sync.js', repoRoot);

function createField(value = '') {
  const listeners = new Map();
  return {
    files: [],
    hidden: true,
    readOnly: false,
    style: { cursor: '', opacity: '' },
    textContent: '',
    value,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    dispatchEvent(event) {
      listeners.get(event.type)?.(event);
    },
  };
}

class FakeFormData {
  constructor() {
    this.entries = [];
  }

  append(name, value) {
    this.entries.push([name, value]);
  }
}

function loadController({ fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({}) }) } = {}) {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-fmu-sync.js',
  });

  const fields = {
    syncButton: createField(),
    keyInput: createField(),
    labSelect: createField(),
    fileInput: createField(),
    fileName: createField(),
    result: createField(),
    description: createField(),
    license: createField(),
    docsUrl: createField(),
    contactEmail: createField(),
    descriptionHint: createField(),
    licenseHint: createField(),
  };
  const toasts = [];
  const controller = context.window.LabManagerFmuSync.createController({
    fields,
    fetchImpl,
    showToast: (message, type) => toasts.push({ message, type }),
    formDataCtor: FakeFormData,
    urlSearchParamsCtor: URLSearchParams,
    encodeURIComponentImpl: encodeURIComponent,
  });
  controller.initialize();
  return { controller, fields, toasts };
}

test('syncs an FMU without a file using the selected lab and metadata query', async () => {
  const calls = [];
  const { fields, toasts } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, status: 200, json: async () => ({ created: true }) };
    },
  });

  fields.keyInput.value = 'spring-damper.fmu';
  fields.labSelect.value = '7';
  fields.description.value = 'A spring damper';
  fields.license.value = 'MIT';
  fields.docsUrl.value = 'https://example.test/docs';
  fields.contactEmail.value = 'ops@example.test';
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  const requestUrl = new URL(calls[0].url, 'http://localhost');
  assert.equal(requestUrl.pathname, '/aas-admin/fmu/spring-damper.fmu/sync');
  assert.equal(requestUrl.searchParams.get('labId'), '7');
  assert.equal(requestUrl.searchParams.get('description'), 'A spring damper');
  assert.equal(requestUrl.searchParams.get('license'), 'MIT');
  assert.equal(requestUrl.searchParams.get('documentationUrl'), 'https://example.test/docs');
  assert.equal(requestUrl.searchParams.get('contactEmail'), 'ops@example.test');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(fields.result.textContent, 'AAS shell synced \u2014 created');
  assert.deepEqual(toasts.at(-1), { message: 'FMU AAS sync: spring-damper.fmu ok', type: 'success' });
});

test('uses multipart upload when an AASX file is selected', async () => {
  const calls = [];
  const { fields } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, status: 200, json: async () => ({ aasxUpload: true, uploadedAasIds: ['aas-1'], uploadedSubmodelIds: ['sub-1'] }) };
    },
  });

  const file = { name: 'spring-damper.aasx' };
  fields.keyInput.value = 'spring-damper.fmu';
  fields.labSelect.value = '7';
  fields.fileInput.files = [file];
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].url, '/aas-admin/fmu/spring-damper.fmu/sync');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(calls[0].options.body.entries, [['file', file], ['labId', '7']]);
  assert.equal(fields.result.textContent, 'Synced 1 shell(s) + 1 submodel(s) from AASX');
});

test('hydrates FMU hints and clears them when the key is edited', async () => {
  const { fields } = loadController({
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ description: 'FMU description', license: 'MIT' }),
    }),
  });

  fields.keyInput.value = 'spring-damper.fmu';
  fields.keyInput.dispatchEvent({ type: 'change' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fields.description.value, 'FMU description');
  assert.equal(fields.description.readOnly, true);
  assert.equal(fields.descriptionHint.textContent, '\u2139\ufe0f From FMU');

  fields.keyInput.dispatchEvent({ type: 'input' });
  assert.equal(fields.description.value, '');
  assert.equal(fields.description.readOnly, false);
  assert.equal(fields.descriptionHint.hidden, true);
});