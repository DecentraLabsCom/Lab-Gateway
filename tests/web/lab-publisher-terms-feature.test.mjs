import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-terms-feature.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  return {
    id,
    value: '',
    textContent: '',
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    async dispatch(type) {
      return listeners.get(type)?.({ target: this });
    },
  };
}

function loadFeature({ fetchImpl = async () => ({ ok: false, status: 500 }), digestImpl, now = () => new Date('2026-09-15T10:20:30.000Z') } = {}) {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map([
    'labTermsUrl',
    'labTermsVersion',
    'labTermsEffectiveDate',
    'labTermsSha256',
    'labTermsStatus',
  ].map(id => [id, createElement(id)]));
  const document = {
    getElementById: id => elements.get(id) || null,
  };
  const context = vm.createContext({ window: {}, document, console, AbortController });
  vm.runInContext(source, context, { filename: 'lab-publisher-terms-feature.js' });
  const controller = context.window.LabPublisherTermsFeature.createController({
    documentImpl: document,
    fetchImpl,
    digestImpl,
    guessVersionFromUrl: () => 'v-test',
    now,
  });
  return { controller, elements };
}

test('hydrates and resets terms metadata through the public boundary', () => {
  const { controller, elements } = loadFeature();

  controller.hydrate({
    url: 'https://example.test/terms.pdf',
    version: 'v2',
    effectiveDate: '2026-01-01',
    sha256: 'ABCDEF',
  });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    url: 'https://example.test/terms.pdf',
    version: 'v2',
    effectiveDate: '2026-01-01',
    sha256: 'ABCDEF',
  });

  controller.reset();
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    url: '',
    version: '',
    effectiveDate: '',
    sha256: '',
  });
  assert.equal(elements.get('labTermsStatus').textContent, '');
});

test('fetches, hashes and reports terms metadata while preserving URL guards', async () => {
  const fetchCalls = [];
  const { controller, elements } = loadFeature({
    fetchImpl: async (url, options) => {
      fetchCalls.push({ url, options });
      return { ok: true, arrayBuffer: async () => new Uint8Array([1, 2]).buffer };
    },
    digestImpl: async () => new Uint8Array([0xab, 0xcd]).buffer,
  });

  controller.bind();
  elements.get('labTermsUrl').value = 'https://example.test/terms.pdf';
  await elements.get('labTermsUrl').dispatch('blur');

  assert.deepEqual(fetchCalls.map(call => call.url), ['https://example.test/terms.pdf']);
  assert.equal(typeof fetchCalls[0].options.signal?.aborted, 'boolean');
  assert.equal(elements.get('labTermsVersion').value, 'v-test');
  assert.equal(elements.get('labTermsEffectiveDate').value, '2026-09-15');
  assert.equal(elements.get('labTermsSha256').value, 'abcd');
  assert.equal(elements.get('labTermsStatus').textContent, 'Terms metadata auto-filled.');

  elements.get('labTermsUrl').value = 'ftp://example.test/terms.pdf';
  await controller.fetchMetadata();
  assert.equal(elements.get('labTermsStatus').textContent, 'Terms link must be an absolute HTTP(S) URL.');
  assert.equal(elements.get('labTermsVersion').value, '');
  assert.equal(elements.get('labTermsSha256').value, '');
});
