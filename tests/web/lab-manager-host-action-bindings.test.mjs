import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-action-bindings.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-action-bindings.js',
  });
  return context.window.LabManagerHostActionBindings;
}

function createButton(action, host = 'station-a') {
  const row = { dataset: { host } };
  return {
    dataset: { action },
    closest(selector) {
      if (selector === 'button[data-action]') return this;
      if (selector === '.host-row') return row;
      return null;
    },
  };
}

test('routes host operation actions without embedding service logic', () => {
  const events = [];
  const controller = loadModule().createController({
    hostState: { 'station-a': { heartbeat: { status: { localModeEnabled: true } } } },
    callbacks: {
      onEditHost: host => events.push(['edit', host]),
      onPoll: host => events.push(['poll', host]),
      onWakeOnLan: host => events.push(['wol', host]),
      onWinrm: (...args) => events.push(['winrm', ...args]),
      onToggleLocalMode: (...args) => events.push(['local', ...args]),
      onCredentials: host => events.push(['credentials', host]),
      onTrust: host => events.push(['trust', host]),
      onSyncAas: host => events.push(['aas', host]),
    },
  });

  controller.handle({ target: { closest: () => createButton('edit-host') } });
  controller.handle({ target: { closest: () => createButton('poll') } });
  controller.handle({ target: { closest: () => createButton('wol') } });
  controller.handle({ target: { closest: () => createButton('prepare') } });
  controller.handle({ target: { closest: () => createButton('release') } });
  controller.handle({ target: { closest: () => createButton('shutdown') } });
  controller.handle({ target: { closest: () => createButton('toggle-local-mode') } });
  controller.handle({ target: { closest: () => createButton('set-winrm-credentials') } });
  controller.handle({ target: { closest: () => createButton('manage-winrm-trust') } });
  controller.handle({ target: { closest: () => createButton('sync-aas') } });

  assert.deepEqual(JSON.parse(JSON.stringify(events)), [
    ['edit', 'station-a'],
    ['poll', 'station-a'],
    ['wol', 'station-a'],
    ['winrm', 'station-a', 'prepare-session', ['--guard-grace=90']],
    ['winrm', 'station-a', 'release-session', ['--reboot']],
    ['winrm', 'station-a', 'power', ['shutdown', '--delay=60', '--reason=Remote order']],
    ['local', 'station-a', false],
    ['credentials', 'station-a'],
    ['trust', 'station-a'],
    ['aas', 'station-a'],
  ]);
});

test('binds the delegated handler once to the host list', () => {
  let listener;
  const hostListEl = {
    addEventListener(type, callback) {
      assert.equal(type, 'click');
      listener = callback;
    },
  };
  const controller = loadModule().createController({ hostListEl });

  controller.bind();
  assert.equal(listener, controller.handle);
});
