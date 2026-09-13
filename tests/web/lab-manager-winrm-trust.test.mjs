import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-winrm-trust.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-trust.js',
  });
  return context.window.LabManagerWinrmTrust;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

class FakeFormData {
  constructor() { this.entries = []; }
  append(name, value, filename) { this.entries.push({ name, value, filename }); }
}

test('loads and previews WinRM trust through the existing endpoints', async () => {
  const module = loadModule();
  const events = [];
  const requests = [];
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      requests.push({ url, options });
      if (url.endsWith('/winrm-trust/preview')) {
        return response({
          preview: {
            status: 'ready',
            fingerprintSha256: 'sha-256-value',
            trustRef: 'station-7',
          },
        });
      }
      return response({ trust: { status: 'missing' } });
    },
    formDataCtor: FakeFormData,
    callbacks: {
      onLoaded: (host, trust) => events.push(['loaded', host, trust.status]),
      onPreview: preview => events.push(['preview', preview.status]),
      onReady: preview => events.push(['ready', preview.valid]),
      onPreviewFinished: () => events.push('finished'),
    },
  });
  const file = { name: 'station.pem' };

  assert.equal(await controller.load('station-7'), true);
  assert.equal(await controller.preview('station-7', file), true);

  assert.equal(requests[0].url, '/ops/api/hosts/station-7/winrm-trust');
  assert.equal(requests[1].url, '/ops/api/hosts/station-7/winrm-trust/preview');
  assert.equal(requests[1].options.method, 'POST');
  assert.deepEqual(requests[1].options.body.entries, [{
    name: 'certificate', value: file, filename: 'station.pem',
  }]);
  assert.deepEqual(events, [
    ['loaded', 'station-7', 'missing'],
    ['preview', 'ready'],
    ['ready', true],
    'finished',
  ]);
});

test('saves and removes WinRM trust with the existing multipart and DELETE contracts', async () => {
  const module = loadModule();
  const events = [];
  const requests = [];
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      requests.push({ url, options });
      return response({});
    },
    formDataCtor: FakeFormData,
    callbacks: {
      onSaved: async host => events.push(['saved', host]),
      onRemoved: async host => events.push(['removed', host]),
      onSaveFinished: () => events.push('save-finished'),
      onRemoveFinished: () => events.push('remove-finished'),
    },
  });
  const file = { name: 'station.pem' };
  const preview = { fingerprintSha256: 'sha-256-value', trustRef: 'station-7' };

  assert.equal(await controller.save('station-7', file, preview), true);
  assert.equal(await controller.remove('station-7'), true);

  assert.equal(requests[0].url, '/ops/api/hosts/station-7/winrm-trust');
  assert.equal(requests[0].options.method, 'PUT');
  assert.deepEqual(requests[0].options.body.entries, [
    { name: 'certificate', value: file, filename: 'station.pem' },
    { name: 'fingerprintSha256', value: 'sha-256-value', filename: undefined },
    { name: 'trustRef', value: 'station-7', filename: undefined },
  ]);
  assert.equal(requests[1].options.method, 'DELETE');
  assert.deepEqual(events, [
    ['saved', 'station-7'],
    'save-finished',
    ['removed', 'station-7'],
    'remove-finished',
  ]);
});
