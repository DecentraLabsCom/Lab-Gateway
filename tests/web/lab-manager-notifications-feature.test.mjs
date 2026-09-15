import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-notifications-feature.js', repoRoot);

test('notifications feature owns controller creation and exposes its access boundary', () => {
  const calls = [];
  const document = {};
  const notificationsController = {
    initialize: () => calls.push('initialize'),
    requestAccess: () => calls.push('requestAccess'),
  };
  const window = {
    LabManagerNotifications: {
      createController: (options) => {
        calls.push('create');
        assert.equal(options.documentImpl, document);
        assert.equal(options.fetchImpl(), 'fetch-result');
        assert.equal(options.showToast('message', 'info'), 'toast-result');
        assert.equal(options.getAuthTokenHandler(), 'auth-handler');
        return notificationsController;
      },
    },
  };
  const context = vm.createContext({
    document,
    window,
    console,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-feature.js',
  });
  const controller = context.window.LabManagerNotificationsFeature.createController({
    documentImpl: document,
    fetchImpl: () => 'fetch-result',
    showToast: () => 'toast-result',
    getAuthTokenHandler: () => 'auth-handler',
  });

  controller.initialize();
  controller.requestAccess();
  assert.deepEqual(calls, ['create', 'initialize', 'requestAccess']);
});
