import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-status.js', repoRoot);

function loadStatus() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-status.js',
  });
  return context.window.LabManagerPowerStatus.createController();
}

test('merges live discovery and outlet states into the existing controller catalog', () => {
  const status = loadStatus();
  const merged = status.mergePowerControllerStatuses([
    {
      id: 'pdu-1',
      name: 'Main PDU',
      outlets: [
        { outlet: '1', displayName: 'PLC', state: 'unknown' },
        { outlet: '2', displayName: 'HMI', state: 'unknown' },
      ],
    },
  ], [
    {
      id: 'pdu-1',
      discovery: { reachable: true },
      outlets: [{ outlet: '1', state: 'on' }],
    },
  ]);

  assert.deepEqual(JSON.parse(JSON.stringify(merged)), [{
    id: 'pdu-1',
    name: 'Main PDU',
    discovery: { reachable: true },
    outlets: [
      { outlet: '1', displayName: 'PLC', state: 'on' },
      { outlet: '2', displayName: 'HMI', state: 'unknown' },
    ],
  }]);
});

test('keeps controllers without a matching live status unchanged', () => {
  const status = loadStatus();
  const controller = { id: 'pdu-1', outlets: [{ outlet: '1', state: 'on' }] };
  const merged = status.mergePowerControllerStatuses([controller], [{ id: 'pdu-2', outlets: [] }]);

  assert.equal(merged[0], controller);
});

test('normalizes missing status collections without inventing discovery data', () => {
  const status = loadStatus();
  const merged = status.mergePowerControllerStatuses([
    { id: 'pdu-1', outlets: [{ outlet: '1', state: 'on' }] },
  ], [{ id: 'pdu-1', discovery: null, outlets: null }]);

  assert.deepEqual(JSON.parse(JSON.stringify(merged)), [{
    id: 'pdu-1',
    discovery: {},
    outlets: [{ outlet: '1', state: 'unknown' }],
  }]);
});
