import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-energy-feature.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  return {
    id,
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    textContent: '',
    innerHTML: '',
    addEventListener: (type, handler) => listeners.set(type, handler),
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
    appendChild: () => {},
  };
}

function loadFeature({ loadManagedLabsOnceImpl = () => Promise.resolve() } = {}) {
  const elements = new Map([
    'refreshPowerCredentialsBtn',
    'powerControllerList',
    'powerControllerSelect',
    'powerCredentialsList',
    'powerCredentialSelect',
    'powerPolicyLabSelect',
    'powerPolicySelect',
    'fmuSyncKey',
    'aasLinkKey',
  ].map((id) => [id, createElement(id)]));
  const document = {
    querySelector: (selector) => elements.get(selector.slice(1)) || null,
    createElement: (tagName) => createElement(tagName),
  };
  const calls = [];
  const managedLabs = [{ labId: 'lab-7', name: 'Thermal Lab' }];
  let policyOptions;
  const powerControllers = {
    initialize: () => calls.push('power-controllers.initialize'),
    load: (...args) => calls.push(['power-controllers.load', ...args]),
    loadStatuses: (...args) => calls.push(['power-controllers.loadStatuses', ...args]),
    getControllers: () => [],
    setCredentials: () => calls.push('power-controllers.setCredentials'),
  };
  const powerPolicies = {
    initialize: () => calls.push('power-policies.initialize'),
    load: (...args) => calls.push(['power-policies.load', ...args]),
    renderSteps: () => {},
  };
  const powerCredentials = {
    initialize: () => calls.push('power-credentials.initialize'),
    load: (...args) => calls.push(['power-credentials.load', ...args]),
  };
  const digitalTwins = {
    initialize: () => calls.push('digital-twins.initialize'),
    getManagedLabs: () => managedLabs,
    loadManagedLabsOnce: (...args) => {
      calls.push(['digital-twins.loadManagedLabsOnce', ...args]);
      return loadManagedLabsOnceImpl?.(...args);
    },
    resolveLabDisplayName: (lab) => `resolved:${lab.labId}`,
  };
  const createModule = (controller, name) => ({
    createController: (options) => {
      calls.push(`${name}.create`);
      if (name === 'power-policies') {
        policyOptions = options;
      }
      if (name === 'power-credentials') {
        options.renderControllerCredentialOptions([]);
      }
      return controller;
    },
  });
  const window = {
    LabManagerFmuSync: createModule({}, 'fmu-sync'),
    LabManagerAasLink: createModule({}, 'aas-link'),
    LabManagerAasx: createModule({}, 'aasx'),
    LabManagerDigitalTwins: createModule(digitalTwins, 'digital-twins'),
    LabManagerPowerCredentials: createModule(powerCredentials, 'power-credentials'),
    LabManagerPowerRenderers: createModule({}, 'power-renderers'),
    LabManagerPowerValues: createModule({
      createPowerPolicyStepDraft: () => ({}),
      createPowerControllerOutletDraft: () => ({}),
      parsePowerPolicyInteger: value => Number(value),
    }, 'power-values'),
    LabManagerPowerOperations: createModule({
      buildPowerCommandPayload: () => ({}),
    }, 'power-operations'),
    LabManagerPowerStatus: createModule({
      mergePowerControllerStatuses: controllers => controllers,
    }, 'power-status'),
    LabManagerPowerControllers: createModule(powerControllers, 'power-controllers'),
    LabManagerPowerPolicies: createModule(powerPolicies, 'power-policies'),
  };
  const context = vm.createContext({
    document,
    window,
    console,
    Promise,
    fetch: () => Promise.resolve(),
    FormData: class FormData {},
    URLSearchParams,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-energy-feature.js',
  });
  return { context, elements, calls, managedLabs, getPolicyOptions: () => policyOptions };
}

test('energy feature composes controllers and exposes tab loading boundaries', async () => {
  const { context, elements, calls, managedLabs, getPolicyOptions } = loadFeature();
  const controller = context.window.LabManagerEnergyFeature.createController({
    documentImpl: context.document,
    fetchImpl: () => Promise.resolve(),
    showToast: () => {},
    showOpsWarning: () => {},
    escapeHtml: value => String(value),
  });

  controller.initialize();
  assert.deepEqual(calls.slice(-4), [
    'power-credentials.initialize',
    'power-controllers.initialize',
    'power-policies.initialize',
    'digital-twins.initialize',
  ]);
  assert.deepEqual(getPolicyOptions().getControllers(), []);
  assert.deepEqual(getPolicyOptions().getManagedLabs(), managedLabs);
  assert.equal(getPolicyOptions().resolveLabDisplayName(managedLabs[0]), 'resolved:lab-7');
  assert.equal(controller.hasEnergyTab(), true);
  assert.equal(controller.hasDigitalTwinsTab(), true);
  assert.deepEqual(controller.getManagedLabs(), managedLabs);
  assert.equal(controller.resolveLabDisplayName(managedLabs[0]), 'resolved:lab-7');

  controller.initializeTab('energy');
  controller.initializeTab('digital-twins');
  await Promise.resolve();
  assert.deepEqual(JSON.parse(JSON.stringify(calls.slice(-5))), [
    ['power-controllers.load', { skipAuthPrompt: true }],
    ['power-credentials.load', { skipAuthPrompt: true }],
    ['digital-twins.loadManagedLabsOnce'],
    ['digital-twins.loadManagedLabsOnce'],
    ['power-policies.load', { skipAuthPrompt: true }],
  ]);

  elements.get('refreshPowerCredentialsBtn').dispatchEvent({ type: 'click' });
  assert.equal(calls.at(-1)[0], 'power-credentials.load');
});

test('waits for managed laboratories before loading existing power policies', async () => {
  let resolveLabs;
  const labsReady = new Promise(resolve => {
    resolveLabs = resolve;
  });
  const { context, calls } = loadFeature({
    loadManagedLabsOnceImpl: () => labsReady,
  });
  const controller = context.window.LabManagerEnergyFeature.createController({
    documentImpl: context.document,
    fetchImpl: () => Promise.resolve(),
    showToast: () => {},
    showOpsWarning: () => {},
    escapeHtml: value => String(value),
  });

  controller.initializeTab('energy');
  assert.equal(calls.some(call => call[0] === 'power-policies.load'), false);

  resolveLabs();
  await labsReady;
  assert.equal(calls.at(-1)[0], 'power-policies.load');
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1)[1])), { skipAuthPrompt: true });
});
