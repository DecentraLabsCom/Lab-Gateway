import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-winrm-credentials.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-credentials.js',
  });
  return context.window.LabManagerWinrmCredentials;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('preserves the WinRM credential request and success lifecycle', async () => {
  const module = loadModule();
  const events = [];
  let request;
  const button = { disabled: false };
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      request = { url, options };
      return response({ saved: true });
    },
    callbacks: {
      closeModal: () => events.push('close'),
      loadHostInventory: () => events.push('reload'),
      showToast: (...args) => events.push(args),
    },
  });

  const saved = await controller.save({
    credentialRef: 'station-7',
    user: '.\\LabGatewaySvc',
    password: 'secret-value',
  }, button);

  assert.equal(saved, true);
  assert.equal(request.url, '/ops/api/hosts/winrm-credentials');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), {
    credentialRef: 'station-7',
    user: '.\\LabGatewaySvc',
    password: 'secret-value',
  });
  assert.deepEqual(events, [
    'close',
    ['WinRM credentials saved', 'success'],
    'reload',
  ]);
  assert.equal(button.disabled, false);
});

test('rejects incomplete WinRM credentials before making a request', async () => {
  const module = loadModule();
  const events = [];
  let requests = 0;
  const controller = module.createController({
    fetchImpl: async () => { requests += 1; return response({}); },
    callbacks: { showToast: (...args) => events.push(args) },
  });

  const saved = await controller.save({ credentialRef: 'station-7', user: '', password: '' });

  assert.equal(saved, false);
  assert.equal(requests, 0);
  assert.deepEqual(events, [[
    'WinRM credential reference, user, and password are required',
    'error',
  ]]);
});
