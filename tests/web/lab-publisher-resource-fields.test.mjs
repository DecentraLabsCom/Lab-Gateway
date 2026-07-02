import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher.js', repoRoot);
const htmlPath = new URL('web/lab-manager/index.html', repoRoot);

function createElement({ id = '', className = '' } = {}) {
  const classes = new Set(className.split(/\s+/).filter(Boolean));
  return {
    id,
    value: '',
    hidden: false,
    readOnly: false,
    innerHTML: '',
    textContent: '',
    checked: false,
    children: [],
    style: {},
    dataset: {},
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
    },
    addEventListener: () => {},
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    querySelectorAll: () => [],
  };
}

function createDocument() {
  const elements = new Map();
  const allElements = [];
  const add = (element) => {
    if (element.id) elements.set(element.id, element);
    allElements.push(element);
    return element;
  };

  [
    'labResourceType',
    'labDetectedResource',
    'labResourcePreview',
    'labSetupMode',
    'fullMetadataPanel',
    'quickMetadataField',
    'fmuConfigTitle',
    'fmuConfigPanel',
    'labAccessKey',
    'labFmuFileName',
    'labAccessURI',
    'labName',
    'labMaxConcurrentUsers',
    'labFmiVersion',
    'labSimulationType',
    'labDefaultStartTime',
    'labDefaultStopTime',
    'labDefaultStepSize',
    'labFmuDescribeStatus',
    'labModelVariablesWrap',
    'labModelVariables',
  ].forEach((id) => add(createElement({ id })));

  add(createElement({ className: 'lab-access-key-field' }));
  add(createElement({ className: 'lab-fmu-file-field' }));

  return {
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (selector) => {
      if (!selector.startsWith('.')) return [];
      const className = selector.slice(1);
      return allElements.filter((element) => element.classList.contains(className));
    },
    createElement: () => createElement(),
    addEventListener: () => {},
  };
}

function loadPublisherHooks({ fetch = async () => { throw new Error('Unexpected fetch call'); } } = {}) {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const instrumented = source.replace(
    /\}\)\(\);\s*$/,
    `
    window.__labPublisherTestHooks = { state, syncResourceTypeFields, applySelectedResource };
})();`
  );
  const document = createDocument();
  const window = { location: { origin: 'https://gateway.example' } };
  const context = vm.createContext({ AbortController, URL, document, fetch, window, console });
  vm.runInContext(instrumented, context, { filename: 'lab-publisher.js' });
  return { document, hooks: context.window.__labPublisherTestHooks };
}

const html = fs.readFileSync(htmlPath, 'utf8');
assert.match(
  html,
  /id="labAccessKey"\s+placeholder="guac:id:42"/,
  'Connection ID placeholder should only describe Guacamole selectors'
);
assert.doesNotMatch(html, /id="labFmuAutoDetectBtn"/, 'FMU metadata should load from the resource dropdown, not a button');

const { document, hooks } = loadPublisherHooks();
hooks.state.status = {
  recommendedRemoteAccessURI: 'https://gateway.example/guacamole',
  recommendedFmuAccessURI: 'https://sarlab.dia.uned.es/fmu',
};

document.getElementById('labResourceType').value = '1';
document.getElementById('labAccessURI').value = 'https://gateway.example/guacamole';
document.getElementById('labFmuFileName').value = 'spring-damper.fmu';
hooks.syncResourceTypeFields();

assert.equal(document.getElementById('labAccessURI').value, 'https://sarlab.dia.uned.es/fmu');
assert.equal(document.getElementById('labAccessURI').readOnly, true);
assert.equal(document.getElementById('labAccessKey').value, 'spring-damper.fmu');

document.getElementById('labResourceType').value = '0';
hooks.syncResourceTypeFields();

assert.equal(document.getElementById('labAccessURI').value, 'https://gateway.example/guacamole');
assert.equal(document.getElementById('labAccessURI').readOnly, true);
assert.equal(document.getElementById('labAccessKey').value, '');

document.getElementById('labAccessURI').value = 'https://lite.example.edu/guacamole';
document.getElementById('labAccessKey').value = 'guac:id:42';
hooks.syncResourceTypeFields();

assert.equal(document.getElementById('labAccessURI').value, 'https://lite.example.edu/guacamole');
assert.equal(document.getElementById('labAccessKey').value, 'guac:id:42');

const fetchCalls = [];
const metadataByFile = {
  'first.fmu': {
    fmiVersion: '2.0',
    simulationType: 'Co-Simulation',
    defaultStartTime: 0,
    defaultStopTime: 5,
    defaultStepSize: 0.1,
    modelVariables: [{ name: 'speed', causality: 'output', type: 'Real', unit: 'm/s', start: 0 }],
  },
  'second.fmu': {
    fmiVersion: '3.0',
    simulationType: 'Model Exchange',
    defaultStartTime: 1,
    defaultStopTime: 9,
    defaultStepSize: 0.25,
    modelVariables: [{ name: 'temperature', causality: 'output', type: 'Real', unit: 'K', start: 293 }],
  },
};
const autoDetect = loadPublisherHooks({
  fetch: async (url, options = {}) => {
    fetchCalls.push({ url: String(url), options });
    if (String(url) === '/lab-admin/fmu/provider-describe-token') {
      return { ok: true, json: async () => ({ token: 'describe-token' }) };
    }
    const parsed = new URL(String(url));
    const fmuFileName = parsed.searchParams.get('fmuFileName');
    return { ok: true, json: async () => metadataByFile[fmuFileName] };
  },
});
autoDetect.hooks.state.status = {
  recommendedRemoteAccessURI: 'https://gateway.example/guacamole',
  recommendedFmuAccessURI: 'https://gateway.example/fmu',
};
autoDetect.hooks.state.fmus = [
  { fileName: 'first.fmu', relativePath: 'test-fmus/first.fmu' },
  { fileName: 'second.fmu', relativePath: 'test-fmus/second.fmu' },
];

autoDetect.document.getElementById('labResourceType').value = '1';
autoDetect.document.getElementById('labDetectedResource').value = '0';
autoDetect.document.getElementById('labName').value = 'stale-name';
autoDetect.document.getElementById('labMaxConcurrentUsers').value = '1';
await autoDetect.hooks.applySelectedResource();

assert.equal(autoDetect.document.getElementById('labName').value, 'first');
assert.equal(autoDetect.document.getElementById('labAccessURI').value, 'https://gateway.example/fmu');
assert.equal(autoDetect.document.getElementById('labAccessKey').value, 'first.fmu');
assert.equal(autoDetect.document.getElementById('labFmuFileName').value, 'first.fmu');
assert.equal(autoDetect.document.getElementById('labFmiVersion').value, '2.0');
assert.match(autoDetect.document.getElementById('labModelVariables').innerHTML, /speed/);

autoDetect.document.getElementById('labDetectedResource').value = '1';
await autoDetect.hooks.applySelectedResource();

assert.equal(autoDetect.document.getElementById('labName').value, 'second');
assert.equal(autoDetect.document.getElementById('labAccessKey').value, 'second.fmu');
assert.equal(autoDetect.document.getElementById('labFmuFileName').value, 'second.fmu');
assert.equal(autoDetect.document.getElementById('labFmiVersion').value, '3.0');
assert.match(autoDetect.document.getElementById('labModelVariables').innerHTML, /temperature/);
assert.doesNotMatch(autoDetect.document.getElementById('labModelVariables').innerHTML, /speed/);
assert.equal(fetchCalls.filter(call => call.url === '/lab-admin/fmu/provider-describe-token').length, 2);
assert.equal(fetchCalls.filter(call => call.url.includes('/api/v1/simulations/describe')).length, 2);
