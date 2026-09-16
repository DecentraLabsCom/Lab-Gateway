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
    options: [],
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
    fileInput: createField(),
    fileName: createField(),
    result: createField(),
    contactEmail: createField(),
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

test('prefers the FMU description over the registered laboratory description', async () => {
  const calls = [];
  const { fields, toasts } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      if (String(url).endsWith('/hints')) {
        return { ok: true, status: 200, json: async () => ({ description: 'FMU model description' }) };
      }
      return { ok: true, status: 200, json: async () => ({ created: true }) };
    },
  });

  fields.keyInput.value = '7';
  fields.keyInput.options = [{
    value: '7',
    dataset: {
      labId: '7',
      accessKey: 'spring-damper.fmu',
      resourceType: '1',
      labDescription: 'Registered laboratory description',
      labDocumentation: JSON.stringify([
        'https://example.test/manual.pdf',
        'https://example.test/guide.html',
      ]),
      labLicense: 'https://example.test/terms.html',
    },
  }];
  fields.contactEmail.value = 'ops@example.test';
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  const syncCall = calls.find(({ url }) => url.includes('/sync'));
  const requestUrl = new URL(syncCall.url, 'http://localhost');
  assert.equal(requestUrl.pathname, '/aas-admin/fmu/spring-damper.fmu/sync');
  assert.equal(requestUrl.searchParams.get('labId'), '7');
  assert.equal(requestUrl.searchParams.get('description'), 'FMU model description');
  assert.equal(requestUrl.searchParams.get('license'), 'https://example.test/terms.html');
  assert.deepEqual(
    JSON.parse(requestUrl.searchParams.get('documentationUrls')),
    ['https://example.test/manual.pdf', 'https://example.test/guide.html'],
  );
  assert.equal(requestUrl.searchParams.get('contactEmail'), 'ops@example.test');
  assert.equal(syncCall.options.method, 'POST');
  assert.equal(fields.result.textContent, 'AAS shell synced \u2014 created');
  assert.deepEqual(toasts.at(-1), { message: 'FMU AAS sync: 7 ok', type: 'success' });
});

test('falls back to the registered laboratory description when the FMU has none', async () => {
  const calls = [];
  const { fields } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      if (String(url).endsWith('/hints')) {
        return { ok: true, status: 200, json: async () => ({ license: 'MIT' }) };
      }
      return { ok: true, status: 200, json: async () => ({ created: true }) };
    },
  });

  fields.keyInput.value = 'spring-damper.fmu';
  fields.keyInput.options = [{
    value: 'spring-damper.fmu',
    dataset: { labId: '7', labDescription: 'Registered laboratory description' },
  }];
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  const requestUrl = new URL(calls.find(({ url }) => url.includes('/sync')).url, 'http://localhost');
  assert.equal(requestUrl.searchParams.get('description'), 'Registered laboratory description');
});

test('uses multipart upload when an AASX file is selected', async () => {
  const calls = [];
  const { fields } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      if (String(url).endsWith('/hints')) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({ aasxUpload: true, uploadedAasIds: ['aas-1'], uploadedSubmodelIds: ['sub-1'] }) };
    },
  });

  const file = { name: 'spring-damper.aasx' };
  fields.keyInput.value = 'spring-damper.fmu';
  fields.keyInput.options = [{
    value: 'spring-damper.fmu',
    dataset: {
      labId: '7',
      labDescription: 'Registered laboratory description',
      labDocumentation: JSON.stringify(['https://example.test/manual.pdf']),
      labLicense: 'https://example.test/terms.html',
    },
  }];
  fields.fileInput.files = [file];
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  const syncCall = calls.find(({ url }) => url.includes('/sync'));
  assert.equal(syncCall.url, '/aas-admin/fmu/spring-damper.fmu/sync');
  assert.equal(syncCall.options.method, 'POST');
  assert.deepEqual(calls.find(({ url }) => url.includes('/sync')).options.body.entries, [
    ['file', file],
    ['labId', '7'],
    ['description', 'Registered laboratory description'],
    ['license', 'https://example.test/terms.html'],
    ['documentationUrls', JSON.stringify(['https://example.test/manual.pdf'])],
  ]);
  assert.equal(fields.result.textContent, 'Synced 1 shell(s) + 1 submodel(s) from AASX');
});

test('does not request FMU-supplied license metadata', async () => {
  const calls = [];
  const { fields } = loadController({
    fetchImpl: async (url) => {
      calls.push(String(url));
      return { ok: true, status: 200, json: async () => ({ license: 'MIT' }) };
    },
  });

  fields.keyInput.value = 'spring-damper.fmu';
  fields.keyInput.options = [{ value: 'spring-damper.fmu', dataset: { labId: '7' } }];
  fields.keyInput.dispatchEvent({ type: 'change' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.length, 1);
  assert.match(calls[0], /\/hints$/);
});

test('reports a disabled AAS deployment instead of treating it as a successful update', async () => {
  const { fields, toasts } = loadController({
    fetchImpl: async (url) => {
      if (String(url).endsWith('/hints')) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ disabled: true, created: false, updated: false }),
      };
    },
  });

  fields.keyInput.value = 'spring-damper.fmu';
  fields.keyInput.options = [{ value: 'spring-damper.fmu', dataset: { labId: '7' } }];
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(fields.result.textContent, 'AAS synchronization is disabled on this gateway.');
  assert.deepEqual(toasts.at(-1), {
    message: 'FMU AAS sync disabled: 7',
    type: 'error',
  });
});

test('synchronizes a physical laboratory from Gateway metadata and heartbeat', async () => {
  const calls = [];
  const { fields, toasts } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, status: 200, json: async () => ({ created: true }) };
    },
  });

  fields.keyInput.value = '42';
  fields.keyInput.options = [{
    value: '42',
    dataset: {
      labId: '42',
      resourceType: '0',
      labDescription: 'Remote laboratory description',
      labDocumentation: JSON.stringify(['https://example.test/manual.pdf']),
      labLicense: 'https://example.test/terms.html',
      accessKey: 'guac:id:42',
    },
  }];
  fields.contactEmail.value = 'lab@example.test';
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/aas-admin/lab/42/sync');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    includeHeartbeat: true,
    metadata: {
      description: 'Remote laboratory description',
      license: 'https://example.test/terms.html',
      documentationUrls: ['https://example.test/manual.pdf'],
      contactEmail: 'lab@example.test',
    },
  });
  assert.equal(fields.result.textContent, 'AAS shell synced — created');
  assert.deepEqual(toasts.at(-1), {
    message: 'Physical laboratory AAS sync: 42 ok',
    type: 'success',
  });
});

test('uploads a custom AASX for a physical laboratory through the generic AAS admin route', async () => {
  const calls = [];
  const { fields } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, status: 200, json: async () => ({
        aasxUpload: true,
        uploadedAasIds: ['urn:decentralabs:lab:42'],
        uploadedSubmodelIds: ['urn:example:submodel'],
      }) };
    },
  });

  const file = { name: 'remote-lab.aasx' };
  fields.keyInput.value = '42';
  fields.keyInput.options = [{
    value: '42',
    dataset: { labId: '42', resourceType: '0' },
  }];
  fields.fileInput.files = [file];
  fields.syncButton.dispatchEvent({ type: 'click' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(calls[0].url, '/aas-admin/aas/42/sync');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(calls[0].options.body.entries.slice(0, 2), [
    ['file', file],
    ['labId', '42'],
  ]);
  assert.equal(fields.result.textContent, 'Synced 1 shell(s) + 1 submodel(s) from AASX');
});
