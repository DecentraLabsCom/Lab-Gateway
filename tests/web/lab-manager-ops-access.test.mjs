import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-ops-access.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-ops-access.js',
  });
  return context.window.LabManagerOpsAccess;
}

function element() {
  return {
    textContent: '',
    innerHTML: '',
    style: {},
    disabled: false,
  };
}

function response(status, ok = status >= 200 && status < 300) {
  return { status, ok };
}

test('refreshes the Lab Manager session with the existing protected request', async () => {
  const module = loadModule();
  const requests = [];
  const controller = module.createController({
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return response(204);
    },
    opsHintEl: element(),
    refreshHostsBtn: element(),
    timelineBtn: element(),
    groupCandidates: () => [],
    logger: { warn() {} },
  });

  assert.equal(await controller.refreshSession(), true);
  assert.deepEqual(JSON.parse(JSON.stringify(requests)), [{
    url: '/lab-manager/access-policy',
    options: { credentials: 'same-origin', cache: 'no-store', skipAuthPrompt: true },
  }]);
});

test('reports inventory candidates and disables operations on policy denial', async () => {
  const module = loadModule();
  const hint = element();
  const refresh = element();
  const timeline = element();
  const controller = module.createController({
    fetchImpl: async () => response(403, false),
    opsHintEl: hint,
    refreshHostsBtn: refresh,
    timelineBtn: timeline,
    groupCandidates: candidates => candidates.map(candidate => candidate.hostname),
    logger: { warn() {} },
  });

  controller.updateHint({
    guacamoleAvailable: true,
    guacamoleUnmatched: [{ hostname: 'station-1' }, { hostname: 'station-2' }],
  });
  assert.match(hint.textContent, /2 Lab Station candidates/);
  assert.equal(await controller.checkAvailability(), false);
  assert.equal(refresh.disabled, true);
  assert.equal(timeline.disabled, true);
  assert.match(hint.innerHTML, /Access policy/);
});
