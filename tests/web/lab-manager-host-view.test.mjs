import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-view.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-view.js',
  });
  return context.window.LabManagerHostView;
}

function element() {
  const listeners = new Map();
  return {
    children: [],
    classList: { add() {}, remove() {} },
    dataset: {},
    innerHTML: '',
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    listener(type) {
      return listeners.get(type);
    },
    querySelector() {
      return null;
    },
  };
}

function createController(overrides = {}) {
  const hostListEl = element();
  const candidateListEl = element();
  const candidateState = {};
  const hostRenderersController = {
    buildHostRow: (host, state, metadata) => ({ kind: 'host', host, state, metadata }),
    buildGuacamoleCandidateRow: (station, state) => ({ kind: 'candidate', station, state }),
  };
  const controller = loadModule().createController({
    hostListEl,
    candidateListEl,
    getHostNames: () => ['host-a', 'host-b'],
    hostState: { 'host-a': { ready: true } },
    hostMetadata: { 'host-a': { editable: true } },
    candidateState,
    hostRenderersController,
    documentImpl: { body: element(), documentElement: { clientWidth: 1024, clientHeight: 768 } },
    windowImpl: {
      innerWidth: 1024,
      innerHeight: 768,
      addEventListener() {},
      removeEventListener() {},
      clearTimeout() {},
      setTimeout: callback => { callback(); return 1; },
    },
    callbacks: {
      onConfigureCandidate: key => { overrides.events?.push(['configure', key]); },
      onProbeCandidate: async (key, station) => { overrides.events?.push(['probe', key, station]); },
    },
  });
  return { candidateState, candidateListEl, controller, hostListEl };
}

function popoverElement({ rect = {}, width = 160, height = 56 } = {}) {
  const listeners = new Map();
  const classes = new Set();
  const element = {
    children: [],
    classList: {
      add: className => classes.add(className),
      remove: className => classes.delete(className),
      contains: className => classes.has(className),
    },
    offsetWidth: width,
    offsetHeight: height,
    parentElement: null,
    style: {},
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    },
    getBoundingClientRect() {
      return {
        left: rect.left ?? 0,
        top: rect.top ?? 0,
        right: rect.right ?? 0,
        bottom: rect.bottom ?? 0,
        width: rect.width ?? 0,
        height: rect.height ?? 0,
      };
    },
    listener(type) {
      return listeners.get(type);
    },
    matches() {
      return false;
    },
    remove() {
      if (!this.parentElement) return;
      this.parentElement.children = this.parentElement.children.filter(child => child !== this);
      this.parentElement = null;
    },
    querySelector(selector) {
      return this.children.find(child => child.selector === selector) || null;
    },
  };
  return element;
}

test('groups Lab Station candidates and remembers the first discovery draft', () => {
  const { candidateState, controller } = createController();
  const candidates = [
    { id: 1, hostname: 'Station-A', name: 'Lab A', selector: 'guac:1' },
    { id: 2, hostname: 'station-a', name: 'Lab A' },
    { id: 3, hostname: '', name: 'Fallback' },
  ];

  const groups = controller.groupCandidates(candidates);
  assert.deepEqual(JSON.parse(JSON.stringify(groups)), [
    {
      key: 'host:station-a',
      address: 'Station-A',
      nameCandidates: ['Lab A'],
      connections: candidates.slice(0, 2),
    },
    {
      key: 'connection:3',
      address: '',
      nameCandidates: ['Fallback'],
      connections: [candidates[2]],
    },
  ]);

  controller.rememberCandidate(candidates[0]);
  controller.rememberCandidate({ ...candidates[0], name: 'Other name' });
  assert.deepEqual(JSON.parse(JSON.stringify(candidateState['host:station-a'])), {
    candidate: candidates[0],
    connectionId: 1,
  });
});

test('renders hosts and delegates candidate actions through the view controller', async () => {
  const events = [];
  const { candidateListEl, controller, hostListEl } = createController({ events });
  const station = {
    key: 'host:station-a',
    address: 'station-a',
    nameCandidates: ['Lab A'],
    connections: [{ id: 1, hostname: 'station-a' }],
  };

  controller.renderHosts();
  assert.deepEqual(hostListEl.children.map(row => row.host), ['host-a', 'host-b']);

  controller.renderCandidates([station]);
  assert.equal(candidateListEl.children.length, 1);
  assert.equal(candidateListEl.children[0].station, station);

  await controller.handleCandidateActions({
    target: {
      closest: () => ({
        dataset: { action: 'configure-candidate' },
        closest: () => ({ dataset: { stationKey: station.key } }),
      }),
    },
  });
  await controller.handleCandidateActions({
    target: {
      closest: () => ({
        dataset: { action: 'probe-candidate' },
        closest: () => ({ dataset: { stationKey: station.key } }),
      }),
    },
  });

  assert.equal(JSON.stringify(events[0]), JSON.stringify(['configure', station.key]));
  assert.equal(events[1][0], 'probe');
  assert.equal(events[1][1], station.key);
  assert.equal(events[1][2], station);
});

test('renders the readiness tooltip outside the scrolling host list and below a top-edge trigger', () => {
  const trigger = popoverElement({
    rect: { left: 240, top: 4, bottom: 28, width: 72, height: 24 },
  });
  trigger.selector = '.ready-indicator';
  const tooltip = popoverElement({ width: 220, height: 64 });
  tooltip.selector = '.ready-indicator-tooltip';
  const row = popoverElement();
  row.children = [trigger, tooltip];
  const hostListEl = popoverElement();
  const candidateListEl = popoverElement();
  const body = popoverElement();
  const hostRenderersController = {
    buildHostRow: () => row,
    buildGuacamoleCandidateRow: () => popoverElement(),
  };
  const controller = loadModule().createController({
    hostListEl,
    candidateListEl,
    getHostNames: () => ['station-top-edge'],
    hostState: {},
    hostMetadata: {},
    candidateState: {},
    hostRenderersController,
    documentImpl: { body, documentElement: { clientWidth: 1024, clientHeight: 768 } },
    windowImpl: {
      innerWidth: 1024,
      innerHeight: 768,
      addEventListener() {},
      removeEventListener() {},
      clearTimeout() {},
      setTimeout: callback => { callback(); return 1; },
    },
  });

  controller.renderHosts();
  trigger.listener('mouseenter')();

  assert.equal(tooltip.parentElement, body);
  assert.equal(tooltip.classList.contains('is-visible'), true);
  assert.equal(tooltip.style.top, '36px');
});

test('wires the active-session tooltip through the same fixed popover controller', () => {
  const trigger = popoverElement({
    rect: { left: 240, top: 4, bottom: 28, width: 72, height: 24 },
  });
  trigger.selector = '.active-session-indicator';
  const tooltip = popoverElement({ width: 220, height: 64 });
  tooltip.selector = '.active-session-tooltip';
  const row = popoverElement();
  row.children = [trigger, tooltip];
  const hostListEl = popoverElement();
  const candidateListEl = popoverElement();
  const body = popoverElement();
  const hostRenderersController = {
    buildHostRow: () => row,
    buildGuacamoleCandidateRow: () => popoverElement(),
  };
  const controller = loadModule().createController({
    hostListEl,
    candidateListEl,
    getHostNames: () => ['station-active-session'],
    hostState: {},
    hostMetadata: {},
    candidateState: {},
    hostRenderersController,
    documentImpl: { body, documentElement: { clientWidth: 1024, clientHeight: 768 } },
    windowImpl: {
      innerWidth: 1024,
      innerHeight: 768,
      addEventListener() {},
      removeEventListener() {},
      clearTimeout() {},
      setTimeout: callback => { callback(); return 1; },
    },
  });

  controller.renderHosts();
  trigger.listener('mouseenter')();

  assert.equal(tooltip.parentElement, body);
  assert.equal(tooltip.classList.contains('is-visible'), true);
});
