import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-provisioning.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-provisioning.js',
  });
  return context.window.LabManagerHostProvisioning;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('preserves the host provisioning request, success message and inventory reload', async () => {
  const module = loadModule();
  const events = [];
  let request;
  const button = { disabled: false };
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      request = { url, options };
      return response({ host: { name: 'station-7' } });
    },
    callbacks: {
      closeModal: () => events.push('close'),
      loadHostInventory: () => events.push('reload'),
      showToast: (...args) => events.push(args),
    },
  });

  assert.equal(await controller.save({
    connectionId: 'connection-7',
    name: 'station-7',
    address: '192.0.2.18',
    mac: '00-11-22-33-44-55',
    labs: ['7'],
    validLabIds: ['7'],
    credentialRef: '192.0.2.18',
    heartbeatPath: 'C:\\LabStation\\heartbeat.json',
  }, button), true);

  assert.equal(request.url, '/ops/api/hosts/provision');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), {
    connectionId: 'connection-7',
    name: 'station-7',
    address: '192.0.2.18',
    mac: '00-11-22-33-44-55',
    labs: ['7'],
    validLabIds: ['7'],
    credentialRef: '192.0.2.18',
    heartbeatPath: 'C:\\LabStation\\heartbeat.json',
  });
  assert.deepEqual(events, [
    'close',
    ['Ops host station-7 configured', 'success'],
    'reload',
  ]);
  assert.equal(button.disabled, false);
});

test('includes a backend request ID in provisioning failures', async () => {
  const module = loadModule();
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => response({ error: 'Internal server error', requestId: 'ops-request-45' }, 500),
    logger: { error() {} },
    callbacks: { showToast: (...args) => events.push(args) },
  });

  assert.equal(await controller.save({ connectionId: 'connection-7', name: 'station-7', address: '192.0.2.18' }), false);
  assert.deepEqual(events, [[
    'Configure host failed: Internal server error (request ID ops-request-45)',
    'error',
  ]]);
});
