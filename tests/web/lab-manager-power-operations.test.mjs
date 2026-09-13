import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-operations.js', repoRoot);

function loadOperations() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-operations.js',
  });
  return context.window.LabManagerPowerOperations.createController();
}

test('builds the existing set_state payload for manual power actions', () => {
  const operations = loadOperations();
  assert.deepEqual(
    JSON.parse(JSON.stringify(operations.buildPowerCommandPayload('on', {
      reason: '  ',
      idempotencyKey: 'lab-manager:key-1',
      protectedOutlet: false,
      maintenance: true,
    }))),
    {
      command: 'set_state',
      state: 'on',
      actor: 'lab-manager',
      reason: 'Lab Manager manual power test',
      idempotencyKey: 'lab-manager:key-1',
      allowProtected: false,
      maintenance: false,
    },
  );
});

test('builds the existing cycle payload and preserves protected maintenance flags', () => {
  const operations = loadOperations();
  assert.deepEqual(
    JSON.parse(JSON.stringify(operations.buildPowerCommandPayload('cycle', {
      offSeconds: 15,
      reason: 'Reservation preparation',
      idempotencyKey: 'lab-manager:key-2',
      protectedOutlet: true,
      maintenance: true,
    }))),
    {
      command: 'cycle',
      actor: 'lab-manager',
      reason: 'Reservation preparation',
      idempotencyKey: 'lab-manager:key-2',
      offSeconds: 15,
      allowProtected: true,
      maintenance: true,
    },
  );
});

test('omits undefined optional command fields without changing the defaults', () => {
  const operations = loadOperations();
  assert.deepEqual(
    JSON.parse(JSON.stringify(operations.buildPowerCommandPayload('off', {
      idempotencyKey: 'lab-manager:key-3',
      protectedOutlet: true,
      maintenance: false,
    }))),
    {
      command: 'set_state',
      state: 'off',
      actor: 'lab-manager',
      reason: 'Lab Manager manual power test',
      idempotencyKey: 'lab-manager:key-3',
      allowProtected: true,
      maintenance: false,
    },
  );
});
