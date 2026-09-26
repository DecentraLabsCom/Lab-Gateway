import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-fmu-station.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-fmu-station.js',
  });
  return context.window.LabManagerFmuStation;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function status({ linked = false } = {}) {
  return {
    configured: true,
    stationHost: 'lab-ws-01',
    stationAddress: '192.168.1.50',
    linked,
    linkedHost: linked ? 'lab-ws-01' : '',
    runner: { status: linked ? 'UP' : 'DEGRADED', stationAuthenticated: linked },
  };
}

test('links the configured FMU Station host and refreshes the global state', async () => {
  const module = loadModule();
  const calls = [];
  const stateChanges = [];
  const events = [];
  let linked = false;
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith('/enroll')) {
        linked = true;
        return response({ enrolled: true, host: 'lab-ws-01' });
      }
      return response(status({ linked }));
    },
    onStateChanged: state => stateChanges.push(state),
    showLoadingToast: message => events.push([message, 'loading']),
    showToast: (...args) => events.push(args),
  });

  await controller.initialize();
  const linkedResult = await controller.link('lab-ws-01');

  assert.equal(linkedResult, true);
  assert.equal(calls[0].url, '/ops/api/fmu/station');
  assert.equal(calls[1].url, '/ops/api/fmu/station/enroll');
  assert.equal(calls[2].url, '/ops/api/fmu/station');
  assert.deepEqual(JSON.parse(calls[1].options.body), { host: 'lab-ws-01' });
  assert.equal(controller.getState().linked, true);
  assert.deepEqual(events, [
    ['Linking FMU token on lab-ws-01...', 'loading'],
    ['FMU token linked on lab-ws-01; background service restarted', 'success'],
  ]);
  assert.equal(stateChanges.some(state => state.busyHost === 'lab-ws-01'), true);
});

test('releases the linked FMU token and does not expose a secret', async () => {
  const module = loadModule();
  const calls = [];
  let linked = true;
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith('/release')) {
        linked = false;
        return response({ released: true, host: 'lab-ws-01' });
      }
      return response(status({ linked }));
    },
    showToast: () => {},
  });

  await controller.initialize();
  assert.equal(await controller.release('lab-ws-01'), true);
  assert.equal(calls[1].url, '/ops/api/fmu/station/release');
  assert.equal(controller.getState().linked, false);
  assert.equal(JSON.stringify(calls).includes('FMU_INTERNAL_TOKEN'), false);
});

test('does not mutate another station when the Gateway already has a link', async () => {
  const module = loadModule();
  const calls = [];
  const events = [];
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(status({ linked: true }));
    },
    showToast: (...args) => events.push(args),
  });

  await controller.initialize();
  assert.equal(await controller.handleAction('lab-ws-02', 'link-fmu'), false);
  assert.equal(calls.length, 1);
  assert.deepEqual(events, [['This station is not the Gateway FMU Station target', 'error']]);
});

test('does not link while the current token state cannot be verified', async () => {
  const module = loadModule();
  const calls = [];
  const events = [];
  const controller = module.createController({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response({
        ...status(),
        linked: false,
        linkStatus: 'unknown',
      });
    },
    showToast: (...args) => events.push(args),
  });

  await controller.initialize();
  assert.equal(await controller.link('lab-ws-01'), false);
  assert.equal(calls.length, 1);
  assert.deepEqual(events, [['FMU token link status cannot be verified right now', 'error']]);
});
