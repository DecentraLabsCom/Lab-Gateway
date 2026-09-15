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

test('uses live device outputs while retaining Gateway safety metadata', () => {
  const merged = loadStatus().mergePowerControllerStatuses([{
    id: 'pdu-1',
    outlets: [{ outlet: '1', logicalName: 'plc', protected: true }],
  }], [{
    id: 'pdu-1',
    discovery: { reachable: true },
    deviceConfiguration: { writable: true, fields: ['name'] },
    outlets: [
      { outlet: '1', deviceName: 'PLC', state: 'on', deviceConfigFields: ['name'] },
      { outlet: '4', deviceName: 'HMI', state: 'off', deviceConfigFields: ['name'] },
    ],
  }]);

  assert.deepEqual(JSON.parse(JSON.stringify(merged[0].outlets)), [
    {
      outlet: '1',
      logicalName: 'plc',
      protected: true,
      deviceName: 'PLC',
      state: 'on',
      deviceConfigFields: ['name'],
      deviceManaged: true,
    },
    {
      outlet: '4',
      deviceName: 'HMI',
      state: 'off',
      deviceConfigFields: ['name'],
      deviceManaged: true,
    },
  ]);
});
