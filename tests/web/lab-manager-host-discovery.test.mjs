import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-discovery.js', repoRoot);

function loadDiscoveryModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-discovery.js',
  });
  return context.window.LabManagerHostDiscovery;
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

test('probes a Guacamole candidate with the existing request and stores the discovery draft', async () => {
  const module = loadDiscoveryModule();
  const candidateState = {};
  const events = [];
  const loadingEvents = [];
  let request;
  const station = {
    address: '192.0.2.18',
    connections: [{ id: 'connection-7', hostname: 'station-7', protocol: 'rdp', port: 3389 }],
  };
  const button = { disabled: false };
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      request = { url, options };
      return response({
        status: 'labstation-detected',
        connection: { id: 'connection-7', hostname: 'station-7' },
        checks: { labStationHttp: { url: 'http://192.0.2.18:8080/health' } },
        opsHostDraft: { mac: '00-11-22-33-44-55', name: 'station-7' },
      });
    },
    candidateState,
    callbacks: {
      renderCandidates: () => events.push('render'),
      loadHostInventory: () => events.push('reload'),
      showLoadingToast: message => loadingEvents.push(message),
      showToast: (...args) => events.push(args),
    },
  });

  await controller.probe('host:station-7', station, button);

  assert.equal(request.url, '/ops/api/hosts/discover');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), { connectionId: 'connection-7' });
  assert.equal(button.disabled, true);
  assert.equal(candidateState['host:station-7'].status, 'labstation-detected');
  assert.equal(candidateState['host:station-7'].connectionId, 'connection-7');
  assert.equal(candidateState['host:station-7'].opsHostDraft.mac, '00-11-22-33-44-55');
  assert.equal(
    candidateState['host:station-7'].detail,
    'HTTP health matched at http://192.0.2.18:8080/health Suggested MAC: 00-11-22-33-44-55',
  );
  assert.deepEqual(events, [
    'render',
    ['Discovery finished for station-7', 'success'],
    'reload',
  ]);
  assert.deepEqual(loadingEvents, ['Checking Lab Station…']);
});

test('keeps the candidate in an error state and reloads inventory after a failed probe', async () => {
  const module = loadDiscoveryModule();
  const candidateState = {};
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => response({ error: 'temporary discovery failure' }, 502),
    candidateState,
    logger: { error() {} },
    callbacks: {
      renderCandidates: () => events.push('render'),
      loadHostInventory: () => events.push('reload'),
      showToast: (...args) => events.push(args),
    },
  });

  await controller.probe(
    'connection:connection-8',
    { address: '192.0.2.19', connections: [{ id: 'connection-8' }] },
    null,
  );

  assert.equal(candidateState['connection:connection-8'].status, 'error');
  assert.equal(candidateState['connection:connection-8'].detail, 'temporary discovery failure');
  assert.deepEqual(events, [
    'render',
    ['Lab Station check failed: temporary discovery failure', 'error'],
    'reload',
  ]);
});
