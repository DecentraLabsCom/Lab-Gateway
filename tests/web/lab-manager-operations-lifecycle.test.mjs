import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-operations-lifecycle.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-operations-lifecycle.js',
  });
  return context.window.LabManagerOperationsLifecycle;
}

test('keeps the Operations bootstrap sequence and protected request options', async () => {
  const events = [];
  const controller = loadModule().createController({
    hasHostList: true,
    hasReservationList: true,
    refreshSession: async () => events.push(['session']),
    loadManagedLabs: async options => events.push(['labs', options]),
    checkAvailability: async () => events.push(['availability']),
    loadHostInventory: async options => events.push(['hosts', options]),
    loadActionableReservations: async options => events.push(['reservations', options]),
    loadActivityFeed: async keepExisting => events.push(['activity', keepExisting]),
  });

  await controller.initialize();

  assert.deepEqual(JSON.parse(JSON.stringify(events)), [
    ['session'],
    ['labs', { skipAuthPrompt: true }],
    ['availability'],
    ['hosts', { skipAuthPrompt: true }],
    ['reservations', { skipAuthPrompt: true }],
    ['activity', false],
  ]);
});

test('does not request optional Operations data when its sections are absent', async () => {
  const events = [];
  const controller = loadModule().createController({
    refreshSession: async () => events.push('session'),
    loadManagedLabs: async () => events.push('labs'),
    checkAvailability: async () => events.push('availability'),
    loadHostInventory: async () => events.push('hosts'),
    loadActionableReservations: async () => events.push('reservations'),
    loadActivityFeed: async () => events.push('activity'),
  });

  await controller.initialize();

  assert.deepEqual(JSON.parse(JSON.stringify(events)), ['session', 'labs', 'availability', 'activity']);
});
