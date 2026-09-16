import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-aasx.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  const classes = new Set();
  return {
    id,
    dataset: {},
    disabled: false,
    hidden: false,
    href: '',
    innerHTML: '',
    textContent: '',
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      toggle: (name, force) => {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
      contains: name => classes.has(name),
    },
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    dispatchEvent(event) {
      return listeners.get(event.type)?.(event);
    },
  };
}

function loadController({ fetchImpl, confirmImpl = () => true } = {}) {
  const context = vm.createContext({
    window: {},
    console,
    Promise,
    setTimeout,
    clearTimeout,
    encodeURIComponent,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-aasx.js',
  });

  const fields = {
    packageList: createElement('aasxPackageList'),
    packageStatus: createElement('aasxPackageStatus'),
    refreshButton: createElement('aasxRefreshBtn'),
    viewModal: createElement('aasxViewModal'),
    viewTitle: createElement('aasxViewTitle'),
    viewBody: createElement('aasxViewBody'),
    viewDownload: createElement('aasxViewDownload'),
    viewClose: createElement('aasxViewClose'),
  };
  const calls = [];
  const toasts = [];
  const controller = context.window.LabManagerAasx.createController({
    fields,
    fetchImpl: fetchImpl || (async () => ({ ok: true, status: 200, json: async () => ({ packages: [] }) })),
    showToast: (message, type) => toasts.push({ message, type }),
    confirmImpl,
    resolveLabDisplayName: lab => lab.name || `Lab #${lab.labId}`,
    onRequest: call => calls.push(call),
  });
  controller.initialize();
  return { controller, fields, calls, toasts };
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

test('lists AASX packages together with their managed laboratory', async () => {
  const { controller, fields, calls } = loadController({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return response({
        packages: [{
          labId: '42',
          filename: 'physical-lab.aasx',
          size: 2048,
          updatedAt: '2026-09-16T10:00:00Z',
          shellIds: ['urn:decentralabs:lab:42'],
          submodelIds: ['urn:example:submodel'],
        }],
      });
    },
  });

  controller.setManagedLabs([{ labId: '42', name: 'Industrial Lab' }]);
  await controller.loadPackages({ skipAuthPrompt: true });

  assert.equal(calls[0].url, '/aas-admin/aas/catalog');
  assert.equal(calls[0].options.skipAuthPrompt, true);
  assert.match(fields.packageList.innerHTML, /Industrial Lab/);
  assert.match(fields.packageList.innerHTML, /physical-lab\.aasx/);
  assert.match(fields.packageList.innerHTML, /data-aasx-view="42"/);
  assert.match(fields.packageList.innerHTML, /href="\/aas-admin\/aas\/42\/download"/);
});

test('views an AASX package in the modal and exposes its download link', async () => {
  const { controller, fields } = loadController({
    fetchImpl: async url => {
      if (url.endsWith('/catalog')) return response({ packages: [{ labId: '7', filename: 'model.aasx', size: 12 }] });
      return response({
        labId: '7',
        filename: 'model.aasx',
        size: 12,
        updatedAt: '2026-09-16T10:00:00Z',
        shellIds: ['urn:shell:7'],
        submodelIds: ['urn:submodel:7'],
      });
    },
  });

  await controller.loadPackages();
  fields.packageList.dispatchEvent({
    type: 'click',
    target: { closest: selector => selector === '[data-aasx-view]' ? { dataset: { aasxView: '7' } } : null },
  });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(fields.viewModal.classList.contains('show'), true);
  assert.equal(fields.viewTitle.textContent, 'model.aasx');
  assert.match(fields.viewBody.innerHTML, /urn:shell:7/);
  assert.equal(fields.viewDownload.href, '/aas-admin/aas/7/download');
});

test('deletes an AASX package and reports the operation through the toast', async () => {
  const { controller, fields, toasts, calls } = loadController({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith('/catalog')) return response({ packages: [{ labId: '9', filename: 'old.aasx', size: 10 }] });
      return response({ deleted: true, labId: '9' });
    },
  });

  await controller.loadPackages();
  fields.packageList.dispatchEvent({
    type: 'click',
    target: { closest: selector => selector === '[data-aasx-delete]' ? { dataset: { aasxDelete: '9' } } : null },
  });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(calls[1].url, '/aas-admin/aas/9');
  assert.equal(calls[1].options.method, 'DELETE');
  assert.match(fields.packageList.innerHTML, /No AASX associations registered/);
  assert.deepEqual(toasts.at(-1), { message: 'AASX association removed for laboratory 9', type: 'success' });
});
