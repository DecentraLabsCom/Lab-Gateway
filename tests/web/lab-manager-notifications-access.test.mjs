import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-notifications-access.js', repoRoot);

function loadController({ fetchImpl, authTokenHandler = null }) {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-access.js',
  });

  const events = {
    configs: [],
    locked: [],
    statuses: [],
    statusUpdates: 0,
    toasts: [],
  };
  const controller = context.window.LabManagerNotificationsAccess.createController({
    fetchImpl,
    applyNotificationConfig: (config) => events.configs.push(config),
    setNotificationsLocked: (locked) => events.locked.push(locked),
    setStatus: (status) => events.statuses.push(status),
    updateNotificationStatusAction: () => { events.statusUpdates += 1; },
    showToast: (message, type) => events.toasts.push({ message, type }),
    getAuthTokenHandler: () => authTokenHandler,
  });
  return { controller, events };
}

test('loads notifications once while sharing a pending request', async () => {
  let resolveResponse;
  const calls = [];
  const responsePromise = new Promise((resolve) => {
    resolveResponse = resolve;
  });
  const { controller, events } = loadController({
    fetchImpl: (url, options) => {
      calls.push({ url, options });
      return responsePromise;
    },
  });

  const firstLoad = controller.loadConfig();
  const secondLoad = controller.loadConfig();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/lab-admin/notifications');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[0].options.skipAuthPrompt, true);

  resolveResponse({
    ok: true,
    status: 200,
    json: async () => ({ config: { enabled: true } }),
  });

  assert.equal(await firstLoad, true);
  assert.equal(await secondLoad, true);
  assert.deepEqual(events.configs[0], { enabled: true });
  assert.equal(events.locked.at(-1), false);
  assert.equal(events.statuses.at(-1), 'Loaded');
  assert.deepEqual(events.toasts.at(-1), {
    message: 'Configuration loaded',
    type: 'success',
  });
});

test('prompts for the Lab Manager token after a protected failure', async () => {
  const promptCalls = [];
  let requestCount = 0;
  const authTokenHandler = {
    getTokenConfigForPath: (path) => ({ key: 'lab-manager', path }),
    showTokenModal: (config, onSuccess) => {
      promptCalls.push({ config, onSuccess });
      onSuccess();
    },
  };
  const { controller, events } = loadController({
    authTokenHandler,
    fetchImpl: async () => {
      requestCount += 1;
      return requestCount === 1
        ? { ok: false, status: 401, json: async () => ({}) }
        : { ok: true, status: 200, json: async () => ({ config: { enabled: true } }) };
    },
  });

  assert.equal(await controller.requestAccess(), false);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(promptCalls.length, 1);
  assert.equal(promptCalls[0].config.path, '/lab-admin/notifications');
  assert.equal(controller.hasNotificationAccess(), true);
  assert.equal(events.locked.at(-1), false);
  assert.deepEqual(events.toasts.at(-1), {
    message: 'Configuration loaded',
    type: 'success',
  });
});
