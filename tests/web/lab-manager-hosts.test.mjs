import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-hosts.js', repoRoot);

function loadHostsModule() {
  const context = vm.createContext({
    URL,
    console,
    window: { location: { origin: 'https://gateway.example.test' } },
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-hosts.js',
  });
  return context.window.LabManagerHosts;
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function createState(hostNames = []) {
  let currentHostNames = [...hostNames];
  return {
    hostState: {},
    hostMetadata: {},
    heartbeatSources: {},
    heartbeatStreamErrorShown: {},
    getHostNames: () => currentHostNames,
    setHostNames: next => { currentHostNames = next; },
    getCurrentHostNames: () => currentHostNames,
  };
}

test('loads host inventory, closes stale streams, and starts only ready hosts', async () => {
  const module = loadHostsModule();
  const state = createState(['old-host']);
  const callbacks = {
    renders: 0,
    candidates: [],
    hints: [],
  };
  class FakeEventSource {
    static instances = [];
    static CLOSED = 2;

    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.closed = false;
      FakeEventSource.instances.push(this);
    }

    addEventListener() {}
    close() { this.closed = true; this.readyState = FakeEventSource.CLOSED; }
  }
  state.heartbeatSources['old-host'] = {
    close() { this.closed = true; },
  };
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      callbacks.request = { url, options };
      return response({
        hosts: [
          { name: 'ready-host', winrmConfigured: true, winrmTrustStatus: 'ready' },
          { name: 'untrusted-host', winrmConfigured: true, winrmTrustStatus: 'missing' },
        ],
        guacamoleUnmatched: [{ id: 'candidate-1' }],
      });
    },
    getEventSource: () => FakeEventSource,
    getOrigin: () => 'https://gateway.example.test',
    state,
    callbacks: {
      renderHosts: () => { callbacks.renders += 1; },
      setGuacamoleCandidates: candidates => { callbacks.rawCandidates = candidates; },
      renderGuacamoleCandidates: candidates => { callbacks.candidates = candidates; },
      rememberGuacamoleCandidate: candidate => { callbacks.remembered = candidate; },
      groupGuacamoleCandidates: candidates => candidates.map(candidate => ({ ...candidate, grouped: true })),
      updateOpsHint: hint => { callbacks.hints.push(hint); },
    },
  });

  await controller.loadInventory({ skipAuthPrompt: true });

  assert.deepEqual(callbacks.request, {
    url: '/ops/api/hosts',
    options: { skipAuthPrompt: true },
  });
  assert.deepEqual(state.getCurrentHostNames(), ['ready-host', 'untrusted-host']);
  assert.equal(state.hostMetadata['ready-host'].winrmTrustStatus, 'ready');
  assert.equal(state.heartbeatSources['old-host'], undefined);
  assert.equal(callbacks.renders, 1);
  assert.deepEqual(callbacks.candidates, [{ id: 'candidate-1', grouped: true }]);
  assert.deepEqual(callbacks.rawCandidates, [{ id: 'candidate-1' }]);
  assert.deepEqual(callbacks.remembered, { id: 'candidate-1' });
  assert.equal(FakeEventSource.instances.length, 1);
  assert.match(FakeEventSource.instances[0].url, /host=ready-host/);
  assert.deepEqual(callbacks.hints, [{
    hosts: [
      { name: 'ready-host', winrmConfigured: true, winrmTrustStatus: 'ready' },
      { name: 'untrusted-host', winrmConfigured: true, winrmTrustStatus: 'missing' },
    ],
    guacamoleUnmatched: [{ id: 'candidate-1' }],
  }]);
});

test('reports an explicit inventory refresh failure instead of continuing as if it succeeded', async () => {
  const module = loadHostsModule();
  const state = createState();
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => { throw new Error('inventory unavailable'); },
    state,
    callbacks: {
      showToast: (...args) => events.push(args),
    },
  });

  await controller.refreshAllHosts();

  assert.deepEqual(events, [['Hosts refresh failed: inventory unavailable', 'error']]);
});

test('polls heartbeat with the existing endpoint and updates the shared host state', async () => {
  const module = loadHostsModule();
  const state = createState();
  const events = [];
  const loadingEvents = [];
  let request;
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      request = { url, options };
      return response({ host: 'station-1', heartbeat: { timestamp: '2026-09-13T10:00:00Z' } });
    },
    state,
    callbacks: {
      renderHosts: () => events.push('render'),
      loadActivityFeed: () => events.push('activity'),
      showLoadingToast: message => loadingEvents.push(message),
      showToast: (...args) => events.push(args),
    },
  });

  await controller.pollHeartbeat('station-1');

  assert.equal(request.url, '/ops/api/heartbeat/poll');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.options.body), { host: 'station-1' });
  assert.deepEqual(state.hostState['station-1'], {
    host: 'station-1',
    heartbeat: { timestamp: '2026-09-13T10:00:00Z' },
  });
  assert.deepEqual(events, [
    'render',
    'activity',
    ['Heartbeat station-1 ok', 'success'],
  ]);
  assert.deepEqual(loadingEvents, ['Checking heartbeat for station-1…']);
});

test('supports silent heartbeat polling for operation follow-up refreshes', async () => {
  const module = loadHostsModule();
  const state = createState();
  const loadingEvents = [];
  const toastEvents = [];
  const controller = module.createController({
    fetchImpl: async () => response({ host: 'station-1', heartbeat: { timestamp: '2026-09-13T10:00:01Z' } }),
    state,
    callbacks: {
      renderHosts: () => {},
      loadActivityFeed: () => {},
      showLoadingToast: message => loadingEvents.push(message),
      showToast: (...args) => toastEvents.push(args),
    },
  });

  await controller.pollHeartbeat('station-1', { silent: true });

  assert.deepEqual(loadingEvents, []);
  assert.deepEqual(toastEvents, []);
  assert.equal(state.hostState['station-1'].heartbeat.timestamp, '2026-09-13T10:00:01Z');
});

test('updates local mode immediately without discarding the latest local-session state', () => {
  const module = loadHostsModule();
  const state = createState(['station-1']);
  state.hostState['station-1'] = {
    host: 'station-1',
    heartbeat: {
      timestamp: '2026-09-13T10:00:00Z',
      status: { localSessionActive: true, localModeEnabled: false },
    },
  };
  let renders = 0;
  const controller = module.createController({
    fetchImpl: async () => response({}),
    state,
    callbacks: { renderHosts: () => { renders += 1; } },
  });

  controller.updateLocalModeState('station-1', true);

  assert.equal(renders, 1);
  assert.equal(state.hostState['station-1'].heartbeat.status.localSessionActive, true);
  assert.equal(state.hostState['station-1'].heartbeat.status.localModeEnabled, true);
});

test('formats structured heartbeat failures consistently for manual polling', async () => {
  const module = loadHostsModule();
  const state = createState();
  const events = [];
  const controller = module.createController({
    fetchImpl: async () => response({
      error: 'Lab Station is unreachable over WinRM',
      code: 'WINRM_UNREACHABLE',
      address: '10.192.38.82',
      port: 5986,
    }, 503),
    state,
    callbacks: {
      formatHeartbeatError: (host, payload) => `${host}:${payload.code}`,
      showToast: (...args) => events.push(args),
    },
  });

  await controller.pollHeartbeat('PC-Siemens');

  assert.deepEqual(events, [['PC-Siemens:WINRM_UNREACHABLE', 'error']]);
});

test('keeps an acknowledged local-mode state while SSE still reports an older heartbeat', () => {
  const module = loadHostsModule();
  const state = createState();
  state.hostMetadata['station-1'] = {
    winrmConfigured: true,
    winrmTrustStatus: 'ready',
  };
  class FakeEventSource {
    static CLOSED = 2;

    constructor() {
      this.readyState = 1;
      this.listeners = new Map();
    }

    addEventListener(type, handler) { this.listeners.set(type, handler); }
    emit(type, event) { this.listeners.get(type)?.(event); }
    close() { this.readyState = FakeEventSource.CLOSED; }
  }
  const controller = module.createController({
    fetchImpl: async () => response({}),
    getEventSource: () => FakeEventSource,
    state,
    callbacks: { renderHosts: () => {} },
  });

  controller.startHeartbeatStream('station-1');
  const source = state.heartbeatSources['station-1'];
  controller.updateLocalModeState('station-1', true);
  source.emit('heartbeat', {
    data: JSON.stringify({
      host: 'station-1',
      heartbeat: { status: { localSessionActive: true, localModeEnabled: false } },
    }),
  });

  assert.equal(state.hostState['station-1'].heartbeat.status.localSessionActive, true);
  assert.equal(state.hostState['station-1'].heartbeat.status.localModeEnabled, true);
});

test('keeps the heartbeat stream URL and classifies configuration errors', () => {
  const module = loadHostsModule();
  const state = createState();
  state.hostMetadata['station-1'] = {
    winrmConfigured: true,
    winrmTrustStatus: 'ready',
  };
  const events = [];
  class FakeEventSource {
    static CLOSED = 2;

    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.listeners = new Map();
    }

    addEventListener(type, handler) { this.listeners.set(type, handler); }
    emit(type, event) { this.listeners.get(type)?.(event); }
    close() { this.readyState = FakeEventSource.CLOSED; events.push('close'); }
  }
  const controller = module.createController({
    fetchImpl: async () => response({}),
    getEventSource: () => FakeEventSource,
    getOrigin: () => 'https://gateway.example.test',
    state,
    callbacks: {
      renderHosts: () => events.push('render'),
      loadActivityFeed: () => events.push('activity'),
      isHeartbeatConfigurationError: code => code === 'WINRM_TRUST_REQUIRED',
      formatHeartbeatError: (host, payload) => `${host}:${payload.code}`,
      showToast: (...args) => events.push(args),
    },
  });

  controller.startHeartbeatStream('station-1');
  const source = state.heartbeatSources['station-1'];
  assert.ok(source);
  const url = new URL(source.url);
  assert.equal(url.pathname, '/ops/api/heartbeat/stream');
  assert.equal(url.searchParams.get('host'), 'station-1');
  assert.equal(url.searchParams.get('include_events'), 'false');

  source.emit('heartbeat', {
    data: JSON.stringify({ host: 'station-1', heartbeat: { ready: true } }),
  });
  assert.equal(state.hostState['station-1'].host, 'station-1');
  assert.equal(state.hostState['station-1'].heartbeat.ready, true);
  assert.deepEqual(events, ['render', 'activity']);

  source.emit('error', {
    data: JSON.stringify({ code: 'WINRM_TRUST_REQUIRED' }),
  });
  assert.equal(state.heartbeatSources['station-1'], undefined);
  assert.deepEqual(events, [
    'render',
    'activity',
    'close',
    ['station-1:WINRM_TRUST_REQUIRED', 'error'],
  ]);
});
