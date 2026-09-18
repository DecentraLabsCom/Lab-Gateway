import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-actions.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-actions.js',
  });
  return context.window.LabManagerHostActions;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('preserves the local-mode request, heartbeat refresh and success message', async () => {
  const module = loadModule();
  const events = [];
  let request;
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      request = { url, options };
      return response({ localModeEnabled: true });
    },
    callbacks: {
      pollHeartbeat: async host => events.push(['poll', host]),
      showToast: (...args) => events.push(args),
    },
  });

  await controller.toggleLocalMode('station-7', true);

  assert.equal(request.url, '/ops/api/hosts/local-mode');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), { host: 'station-7', enabled: true });
  assert.deepEqual(events, [
    ['poll', 'station-7'],
    ['Local mode enabled for station-7', 'success'],
  ]);
});

test('applies the local-mode response after a stale heartbeat refresh', async () => {
  const module = loadModule();
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => response({ localModeEnabled: true }),
    callbacks: {
      pollHeartbeat: async host => events.push(['poll', host]),
      updateLocalModeState: (host, enabled) => events.push(['state', host, enabled]),
      showToast: (...args) => events.push(args),
    },
  });

  await controller.toggleLocalMode('station-7', true);

  assert.deepEqual(events, [
    ['poll', 'station-7'],
    ['state', 'station-7', true],
    ['Local mode enabled for station-7', 'success'],
  ]);
});

test('uses the requested local-mode value when an older backend omits it from the response', async () => {
  const module = loadModule();
  const states = [];
  const controller = module.createController({
    fetchImpl: async () => response({}),
    callbacks: {
      updateLocalModeState: (host, enabled) => states.push([host, enabled]),
    },
  });

  await controller.toggleLocalMode('station-7', false);

  assert.deepEqual(states, [['station-7', false]]);
});

test('preserves WoL requests and access/error messages', async () => {
  const module = loadModule();
  const events = [];
  const requests = [];
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return requests.length === 1 ? response({ success: true }) : response({}, 403);
    },
    callbacks: { showToast: (...args) => events.push(args) },
    logger: { error() {} },
  });

  await controller.triggerWol('station-7');
  await controller.triggerWol('station-7');

  assert.equal(requests[0].url, '/ops/api/wol');
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body), { host: 'station-7' });
  assert.equal(requests[1].url, '/ops/api/wol');
  assert.deepEqual(events, [
    ['WoL station-7: sent', 'success'],
    ['Access denied: /ops blocked by Lab Manager access policy', 'error'],
  ]);
});

test('shows the backend WoL validation reason instead of only the HTTP status', async () => {
  const module = loadModule();
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => response({ error: 'mac is required' }, 400),
    callbacks: { showToast: (...args) => events.push(args) },
    logger: { error() {} },
  });

  await controller.triggerWol('PC-Siemens');

  assert.deepEqual(events, [
    ['WoL failed for PC-Siemens: mac is required', 'error'],
  ]);
});

test('shows persistent progress feedback while WoL is pending', async () => {
  const module = loadModule();
  const loadingEvents = [];
  const controller = module.createController({
    fetchImpl: async () => response({ success: true }),
    callbacks: {
      showLoadingToast: message => loadingEvents.push(message),
      showToast: () => {},
    },
  });

  await controller.triggerWol('PC-Siemens');

  assert.deepEqual(loadingEvents, ['Waking PC-Siemens…']);
});

test('refreshes heartbeat after successful Prepare without doing so for failed Release', async () => {
  const module = loadModule();
  const events = [];
  const requests = [];
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return requests.length === 1 ? response({ exit_code: 0 }) : response({}, 500);
    },
    callbacks: {
      pollHeartbeat: async host => events.push(['poll', host]),
      showToast: (...args) => events.push(args),
    },
    logger: { error() {} },
  });

  await controller.triggerWinrm('station-7', 'prepare-session', ['--guard-grace=90']);
  await controller.triggerWinrm('station-7', 'release-session', ['--reboot']);

  assert.deepEqual(JSON.parse(requests[0].options.body), {
    host: 'station-7',
    command: 'prepare-session',
    args: ['--guard-grace=90'],
  });
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    host: 'station-7',
    command: 'release-session',
    args: ['--reboot'],
  });
  assert.deepEqual(events, [
    ['poll', 'station-7'],
    ['prepare-session on station-7: ok', 'success'],
    ['release-session failed on station-7: HTTP 500', 'error'],
  ]);
});

test('preserves AAS sync result classification and request shape', async () => {
  const module = loadModule();
  const events = [];
  const requests = [];
  const responses = [
    response({ labs: [] }),
    response({ labs: [{ disabled: true }, { disabled: true }] }),
    response({ labs: [{ disabled: false, error: 'sync failed' }, { disabled: false }] }),
    response({ labs: [{ disabled: false }, { disabled: false }] }),
  ];
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return responses.shift();
    },
    callbacks: { showToast: (...args) => events.push(args) },
  });

  await controller.syncAasHost('station-7');
  await controller.syncAasHost('station-7');
  await controller.syncAasHost('station-7');
  await controller.syncAasHost('station-7');

  assert.equal(requests.length, 4);
  requests.forEach(({ url, options }) => {
    assert.equal(url, '/ops/api/aas-sync');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { host: 'station-7' });
  });
  assert.deepEqual(events, [
    ['AAS sync station-7: no catalog labs resolved', 'error'],
    ['AAS sync station-7: AAS not configured on this gateway', 'error'],
    ['AAS sync station-7: 1/2 failed', 'error'],
    ['AAS sync station-7: 2 lab(s) synced', 'success'],
  ]);
});
