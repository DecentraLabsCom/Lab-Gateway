import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-lab-actions.js', repoRoot);

function createListElement() {
  const listeners = [];
  const classes = new Set();
  return {
    innerHTML: '',
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
    },
    addEventListener(type, listener) {
      listeners.push({ type, listener });
    },
    dispatchClick(target) {
      const binding = listeners.find(item => item.type === 'click');
      return binding?.listener({ target });
    },
  };
}

function loadFeature({ labs = [] } = {}) {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-lab-actions.js' });

  const listElement = createListElement();
  const calls = [];
  const controller = context.window.LabPublisherLabActions.createController({
    listElement,
    getLabs: () => labs,
    fetchJson: async (url, options) => {
      calls.push({ url, options });
      return { success: true, action: 'unlistLab', status: '0x1', transactionHash: '0xconfirmed' };
    },
    assertLabMutationSuccess: () => {},
    renderLabActionIcon: action => `<svg data-action="${action}"></svg>`,
    escapeHtml: value => String(value ?? ''),
    escapeAttr: value => String(value ?? ''),
    formatRawPriceForUnit: value => String(value),
    resolveLabPriceUnit: () => 'hour',
    resolveLabDisplayName: lab => lab.name || `Lab #${lab.labId}`,
    confirmImpl: () => true,
    getEditingLabId: () => null,
    callbacks: {
      onEdit: lab => calls.push({ type: 'edit', lab }),
      onClearEdit: () => calls.push({ type: 'clear-edit' }),
      onReload: () => calls.push({ type: 'reload' }),
      setStatus: (message, isError) => calls.push({ type: 'status', message, isError }),
    },
  });
  controller.bind();
  return { controller, listElement, calls };
}

test('renders published labs and routes listing mutations through the feature boundary', async () => {
  const { controller, listElement, calls } = loadFeature({
    labs: [{ labId: '42', name: 'StateSpace', listed: true, accessKey: 'guac:id:42', uri: 'https://gateway.example/lab-42', price: '1' }],
  });

  controller.render();

  assert.match(listElement.innerHTML, /data-lab-action="unlist"/);
  await listElement.dispatchClick({
    closest: () => ({ dataset: { labAction: 'unlist', labId: '42' }, disabled: false }),
  });

  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {
    url: '/lab-admin/labs/42/unlist',
    options: { method: 'POST' },
  });
  assert.equal(calls.at(-1).type, 'reload');
  assert.match(calls.find(call => call.type === 'status').message, /Unlisted StateSpace/);
});

test('keeps edit and delete actions behind the controller callbacks and confirmation guard', async () => {
  const { controller, listElement, calls } = loadFeature({
    labs: [{ labId: '7', name: 'Remote Lab', listed: false, accessKey: 'guac:id:7', uri: 'https://gateway.example/lab-7', price: '2' }],
  });
  controller.render();

  await listElement.dispatchClick({
    closest: () => ({ dataset: { labAction: 'edit', labId: '7' }, disabled: false }),
  });
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), { type: 'edit', lab: { labId: '7', name: 'Remote Lab', listed: false, accessKey: 'guac:id:7', uri: 'https://gateway.example/lab-7', price: '2' } });

  await listElement.dispatchClick({
    closest: () => ({ dataset: { labAction: 'delete', labId: '7' }, disabled: false }),
  });
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(call => call.url))), {
    url: '/lab-admin/labs/7',
    options: { method: 'DELETE' },
  });
  assert.equal(calls.at(-1).type, 'reload');
});
