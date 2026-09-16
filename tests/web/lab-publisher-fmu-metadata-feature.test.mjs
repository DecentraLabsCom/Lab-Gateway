import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-fmu-metadata-feature.js', repoRoot);

function createElement(id) {
  return {
    id,
    value: '',
    textContent: '',
    innerHTML: '',
    hidden: false,
    addEventListener() {},
  };
}

function loadFeature({ fetchFmuMetadata = async () => ({}) } = {}) {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map([
    'labFmuFileName',
    'labAccessURI',
    'labFmuDescribeStatus',
    'labFmiVersion',
    'labSimulationType',
    'labDefaultStartTime',
    'labDefaultStopTime',
    'labDefaultStepSize',
    'labName',
    'labModelVariablesWrap',
    'labModelVariables',
  ].map(id => [id, createElement(id)]));
  const document = { getElementById: id => elements.get(id) || null };
  const context = vm.createContext({ window: {}, document, console, AbortController });
  vm.runInContext(source, context, { filename: 'lab-publisher-fmu-metadata-feature.js' });
  const toasts = [];
  const controller = context.window.LabPublisherFmuMetadataFeature.createController({
    documentImpl: document,
    fetchFmuMetadata,
    showToast: (message, type) => toasts.push({ message, type }),
    renderModelVariables: ({ modelVariables }) => ({
      hidden: modelVariables.length === 0,
      html: modelVariables.map(variable => `<span>${variable.name}</span>`).join(''),
    }),
  });
  return { controller, elements, toasts };
}

test('autodetects FMU metadata, reports success and owns the rendered variable state', async () => {
  const calls = [];
  const { controller, elements, toasts } = loadFeature({
    fetchFmuMetadata: async args => {
      calls.push(args);
      return {
        modelName: 'spring-damper',
        fmiVersion: '2.0',
        simulationType: 'Model Exchange',
        defaultStartTime: 0,
        defaultStopTime: 5,
        defaultStepSize: 0.1,
        modelVariables: [{ name: 'speed', type: 'Real' }],
      };
    },
  });

  elements.get('labFmuFileName').value = 'spring-damper.fmu';
  elements.get('labAccessURI').value = 'https://gateway.example/fmu';
  await controller.autoDetect();

  assert.equal(calls.length, 1);
  assert.equal(calls[0].fmuFileName, 'spring-damper.fmu');
  assert.equal(calls[0].gatewayUrl, 'https://gateway.example/fmu');
  assert.equal(typeof calls[0].signal?.aborted, 'boolean');
  assert.equal(elements.get('labName').value, 'spring-damper');
  assert.equal(elements.get('labFmiVersion').value, '2.0');
  assert.equal(elements.get('labSimulationType').value, 'Model Exchange');
  assert.equal(elements.get('labModelVariablesWrap').hidden, false);
  assert.match(elements.get('labModelVariables').innerHTML, /speed/);
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getModelVariables())), [{ name: 'speed', type: 'Real' }]);
  assert.equal(elements.get('labFmuDescribeStatus').textContent, 'FMU metadata loaded successfully.');
  assert.deepEqual(toasts, [{ message: 'FMU metadata loaded', type: 'success' }]);
});

test('reports missing input and failures, then resets the FMU draft', async () => {
  const { controller, elements, toasts } = loadFeature({
    fetchFmuMetadata: async () => { throw new Error('describe failed'); },
  });

  await controller.autoDetect();
  assert.equal(elements.get('labFmuDescribeStatus').textContent, 'Set FMU File Name first.');

  elements.get('labFmuFileName').value = 'broken.fmu';
  elements.get('labAccessURI').value = 'https://gateway.example/fmu';
  await controller.autoDetect();
  assert.equal(elements.get('labFmuDescribeStatus').textContent, 'Auto-detect failed: describe failed');
  assert.deepEqual(toasts, [
    { message: 'Set FMU File Name first.', type: 'error' },
    { message: 'FMU metadata detection failed: describe failed', type: 'error' },
  ]);

  controller.hydrate({
    fmiVersion: '3.0',
    modelVariables: [{ name: 'temperature' }],
  });
  controller.reset(false);
  assert.equal(elements.get('labFmiVersion').value, '');
  assert.equal(elements.get('labModelVariablesWrap').hidden, true);
  assert.equal(elements.get('labModelVariables').innerHTML, '');
  assert.equal(elements.get('labFmuDescribeStatus').textContent, 'Set Access URI and FMU File Name to enable auto-detect.');
});
