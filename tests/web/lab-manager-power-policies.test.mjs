import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-policies.js', repoRoot);

function createField(value = '') {
  return {
    value,
    checked: true,
    disabled: false,
    innerHTML: '',
    children: [],
    addEventListener() {},
    appendChild(child) { this.children.push(child); },
  };
}

function createDraft(step = {}) {
  const action = step.action || 'on';
  return {
    id: step.id || '',
    phase: step.phase || 'pre_start',
    controllerId: step.controllerId || '',
    outlet: step.outlet || '',
    stepLabel: step.stepLabel || '',
    action,
    required: step.required !== false,
    readBackRequired: step.readBackRequired !== false,
    offSeconds: step.offSeconds ?? 10,
    delayBeforeSeconds: step.delayBeforeSeconds ?? 0,
    delayAfterSeconds: step.delayAfterSeconds ?? 0,
    timeoutSeconds: step.timeoutSeconds ?? 20,
    retryCount: step.retryCount ?? 0,
    allowProtected: step.allowProtected === true,
    conditionsText: step.conditionsText || JSON.stringify(step.conditions || {}, null, 2),
  };
}

function parseInteger(value, fieldName, maximum) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > maximum) {
    throw new Error(`${fieldName} must be between 0 and ${maximum}`);
  }
  return parsed;
}

function stepChangeTarget(index, field, value) {
  return {
    dataset: { stepField: field },
    type: 'select',
    value,
    closest: () => ({ dataset: { stepIndex: String(index) } }),
  };
}

function stepDragTarget(index) {
  return {
    closest: () => ({ dataset: { stepIndex: String(index) }, classList: { add() {}, remove() {} } }),
  };
}

function dataTransfer() {
  const values = new Map();
  return {
    dropEffect: '',
    effectAllowed: '',
    setData(type, value) { values.set(type, value); },
    getData(type) { return values.get(type) || ''; },
  };
}

function loadPolicies(overrides = {}) {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-policies.js',
  });
  const fields = {
    select: createField(),
    labSelect: createField('lab-1'),
    name: createField('Policy 1'),
    enabled: createField(),
    respectLocalMode: createField(),
    maintenanceMode: createField(),
    startFailureMode: createField('fail_reservation_start'),
    endFailureMode: createField('warn_and_continue'),
    steps: createField(),
    addStep: createField(),
    saveButton: createField(),
    status: createField(),
    editorHint: createField(),
  };
  const controller = context.window.LabManagerPowerPolicies.createController({
    fields,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ policies: [] }) }),
    showToast() {},
    showOpsWarning() {},
    getControllers: () => [{ id: 'pdu-1', outlets: [{ outlet: '1' }] }],
    getManagedLabs: () => [{ labId: 'lab-1', name: 'Lab One' }],
    resolveLabDisplayName: lab => lab.name || `Lab #${lab.labId}`,
    renderPowerPolicyStepsMarkup: () => '<div>steps</div>',
    createPowerPolicyStepDraft: createDraft,
    parsePowerPolicyInteger: parseInteger,
    documentImpl: { createElement: () => createField() },
    ...overrides,
  });
  return { controller, fields };
}

test('preserves policy form payload normalization and validation messages', () => {
  const { controller, fields } = loadPolicies();
  controller.populateForm({
    policyName: 'Policy 1',
    enabled: true,
    respectLocalMode: true,
    maintenanceMode: false,
    steps: [{ controllerId: 'pdu-1', outlet: '1', action: 'cycle', offSeconds: 15, conditions: { ready: true } }],
  });
  const payload = controller.readForm();
  assert.deepEqual(JSON.parse(JSON.stringify(payload)), {
    policyName: 'Policy 1',
    enabled: true,
    respectLocalMode: true,
    maintenanceMode: false,
    startFailureMode: 'fail_reservation_start',
    endFailureMode: 'warn_and_continue',
    steps: [{
      phase: 'pre_start',
      controllerId: 'pdu-1',
      outlet: '1',
      action: 'cycle',
      required: true,
      readBackRequired: true,
      offSeconds: 15,
      delayBeforeSeconds: 0,
      delayAfterSeconds: 0,
      timeoutSeconds: 20,
      retryCount: 0,
      allowProtected: false,
      conditions: { ready: true },
    }],
  });
  controller.populateForm({ policyName: 'Policy 1', steps: [{ controllerId: 'pdu-1', outlet: '1', action: 'cycle', offSeconds: 0 }] });
  fields.name.value = 'Policy 1';
  assert.throws(() => controller.readForm(), { message: 'Step 1: cycle off time must be greater than zero' });
  fields.name.value = '';
  assert.throws(() => controller.readForm(), { message: 'Policy name is required' });
});

test('derives the target state from action and omits cycle timing for non-cycle steps', () => {
  const { controller } = loadPolicies();
  controller.populateForm({
    policyName: 'Policy 1',
    steps: [{
      controllerId: 'pdu-1',
      outlet: '1',
      action: 'on',
      stepLabel: 'PLC boot',
      offSeconds: 99,
    }],
  });

  const step = controller.readForm().steps[0];
  assert.equal(step.action, 'on');
  assert.equal(step.stepLabel, 'PLC boot');
  assert.equal('desiredState' in step, false);
  assert.equal('offSeconds' in step, false);
});

test('adds policy steps using the first available controller and outlet', () => {
  const { controller, fields } = loadPolicies();
  controller.resetEditor();
  controller.addStep();
  assert.equal(fields.steps.innerHTML, '<div>steps</div>');
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getStepDrafts())), [{
    id: '',
    phase: 'pre_start',
    controllerId: 'pdu-1',
    outlet: '1',
    stepLabel: '',
    action: 'on',
    required: true,
    readBackRequired: true,
    offSeconds: 10,
    delayBeforeSeconds: 0,
    delayAfterSeconds: 0,
    timeoutSeconds: 20,
    retryCount: 0,
    allowProtected: false,
    conditionsText: '{}',
  }]);
});

test('reorders policy steps through drag and drop and preserves that order on save', () => {
  const { controller, fields } = loadPolicies({
    renderPowerPolicyStepsMarkup: steps => steps.map(step => step.stepLabel).join('|'),
  });

  controller.addStep();
  controller.handleStepChange({ target: stepChangeTarget(0, 'stepLabel', 'first') });
  controller.addStep();
  controller.handleStepChange({ target: stepChangeTarget(1, 'stepLabel', 'second') });
  controller.addStep();
  controller.handleStepChange({ target: stepChangeTarget(2, 'stepLabel', 'third') });

  const transfer = dataTransfer();
  controller.handleStepDragStart({ target: stepDragTarget(2), dataTransfer: transfer });
  let prevented = false;
  controller.handleStepDragOver({
    target: stepDragTarget(0),
    dataTransfer: transfer,
    preventDefault() { prevented = true; },
  });
  controller.handleStepDrop({
    target: stepDragTarget(0),
    dataTransfer: transfer,
    preventDefault() { prevented = true; },
  });

  assert.deepEqual(
    JSON.parse(JSON.stringify(controller.getStepDrafts().map(step => step.stepLabel))),
    [
      'third',
      'first',
      'second',
    ],
  );
  assert.equal(prevented, true);
  assert.equal(fields.steps.innerHTML, 'third|first|second');
  assert.deepEqual(
    JSON.parse(JSON.stringify(controller.readForm().steps.map(step => ({ stepLabel: step.stepLabel })))),
    [
      { stepLabel: 'third' },
      { stepLabel: 'first' },
      { stepLabel: 'second' },
    ],
  );
});

test('preserves policy PUT endpoint, body and status lifecycle', async () => {
  const calls = [];
  const { controller, fields } = loadPolicies({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ policies: [] }) };
    },
  });
  controller.populateForm({ policyName: 'Policy 1', steps: [] });
  await controller.save();
  assert.equal(calls[0].url, '/ops/api/power/policies/lab-1');
  assert.equal(calls[0].options.method, 'PUT');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    policyName: 'Policy 1',
    enabled: true,
    respectLocalMode: true,
    maintenanceMode: false,
    startFailureMode: 'fail_reservation_start',
    endFailureMode: 'warn_and_continue',
    steps: [],
    labId: 'lab-1',
  });
  assert.equal(fields.saveButton.disabled, false);
});

test('uses managed laboratory names in existing policy options', async () => {
  const { controller, fields } = loadPolicies({
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ policies: [{ labId: 'lab-1', policyName: 'Lab powering' }] }),
    }),
  });

  await controller.load({ skipAuthPrompt: true });

  assert.equal(fields.select.children[0].textContent, 'Lab One · Lab powering');
});
