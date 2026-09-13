import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-values.js', repoRoot);

function loadValues() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-values.js',
  });
  return context.window.LabManagerPowerValues.createController();
}

test('normalizes power policy drafts and accepts legacy aliases', () => {
  const values = loadValues();
  const draft = values.createPowerPolicyStepDraft({
    stepId: 'step-1',
    phase: ' START ',
    sequence: '20',
    controller_id: 'pdu-1',
    outlet_key: '1',
    logical_name: 'PLC',
    action: ' CYCLE ',
    desired_state: 'unknown',
    read_back_required: false,
    off_seconds: '15',
    delay_before_seconds: '2',
    delay_after_seconds: '3',
    timeout_seconds: '30',
    retry_count: '2',
    allow_protected: true,
    conditions: { ready: true },
  });

  assert.deepEqual(JSON.parse(JSON.stringify(draft)), {
    id: 'step-1',
    phase: 'start',
    sequence: 20,
    controllerId: 'pdu-1',
    outlet: '1',
    logicalName: 'PLC',
    action: 'cycle',
    desiredState: 'unknown',
    required: true,
    readBackRequired: false,
    offSeconds: 15,
    delayBeforeSeconds: 2,
    delayAfterSeconds: 3,
    timeoutSeconds: 30,
    retryCount: 2,
    allowProtected: true,
    conditionsText: '{\n  "ready": true\n}',
  });
});

test('keeps policy and outlet defaults stable for incomplete input', () => {
  const values = loadValues();
  assert.deepEqual(JSON.parse(JSON.stringify(values.createPowerPolicyStepDraft({ action: 'invalid' }))), {
    id: '',
    phase: 'pre_start',
    sequence: 10,
    controllerId: '',
    outlet: '',
    logicalName: '',
    action: 'on',
    desiredState: '',
    required: true,
    readBackRequired: true,
    offSeconds: 10,
    delayBeforeSeconds: 0,
    delayAfterSeconds: 0,
    timeoutSeconds: 20,
    retryCount: 0,
    allowProtected: false,
    conditionsText: '{}',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(values.createPowerControllerOutletDraft({ outletKey: '2', defaultState: 'on', protected: true }))), {
    outlet: '2',
    displayName: '',
    logicalName: '',
    protected: true,
    critical: false,
    defaultState: 'on',
  });
});

test('preserves power policy integer validation messages and bounds', () => {
  const values = loadValues();
  assert.equal(values.parsePowerPolicyInteger('30', 'Timeout', 300), 30);
  assert.throws(() => values.parsePowerPolicyInteger('-1', 'Retries', 5), {
    message: 'Retries must be between 0 and 5',
  });
  assert.throws(() => values.parsePowerPolicyInteger('301', 'Timeout', 300), {
    message: 'Timeout must be between 0 and 300',
  });
});
