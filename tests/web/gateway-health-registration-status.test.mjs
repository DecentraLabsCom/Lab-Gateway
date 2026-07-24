import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/gateway-health.js', repoRoot);
const script = fs.readFileSync(scriptPath, 'utf8');

function createElement() {
  return {
    className: '',
    children: [],
    innerHTML: '',
    textContent: '',
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    querySelector: () => null,
  };
}

function collectElements(element) {
  return [element, ...element.children.flatMap(collectElements)];
}

async function renderHealth(details) {
  const statusIndicator = createElement();
  const statusText = createElement();
  statusIndicator.querySelector = () => statusText;
  const elements = new Map([
    ['topGrid', createElement()],
    ['serviceGrid', createElement()],
    ['infraSection', createElement()],
  ]);

  const document = {
    addEventListener: (event, handler) => {
      if (event === 'DOMContentLoaded') handler();
    },
    querySelector: () => statusIndicator,
    getElementById: (id) => elements.get(id) || null,
    createElement,
  };
  const fetch = async (url) => {
    assert.equal(url, '/gateway/health');
    return {
      text: async () => JSON.stringify({ status: 'UP', public: true }),
    };
  };

  vm.runInNewContext(script, {
    document,
    fetch: async (url) => {
      if (url === '/gateway/health') return fetch(url);
      assert.equal(url, '/gateway/health/details');
      return { json: async () => details };
    },
    console: { error: () => {} },
  });

  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { statusText, serviceGrid: elements.get('serviceGrid') };
}

function baseDetails(blockchainDetails) {
  return {
    status: 'UP',
    mode: 'full',
    lite: false,
    services: {
      blockchain: { ok: true, details: blockchainDetails },
      guacamole: { ok: true },
      guacamole_api: { ok: true },
      guacd: { ok: true },
      guacamole_schema: { ok: true },
      ops: { ok: true },
      mysql: { ok: true },
    },
    infra: { cert: { days_remaining: 30 } },
  };
}

test('renders provider institutions as consumers and removes the redundant institution status', async () => {
  const { serviceGrid } = await renderHealth(baseDetails({
    operating_mode: 'provider-consumer',
    provider_registered: true,
    consumer_registered: true,
  }));
  const rendered = collectElements(serviceGrid);

  assert.equal(rendered.some((element) => element.textContent === 'Institution registered'), false);
  assert.equal(rendered.some((element) => element.textContent === 'Consumer registered'), true);
  assert.equal(rendered.some((element) => element.textContent === 'Provider registered'), true);
  assert.equal(rendered.filter((element) => element.textContent === 'OK').length >= 2, true);
});

test('renders provider as not applicable in consumer-only mode', async () => {
  const { serviceGrid } = await renderHealth(baseDetails({
    operating_mode: 'consumer-only',
    provider_registered: false,
    consumer_registered: true,
  }));
  const rendered = collectElements(serviceGrid);
  const noTag = rendered.find((element) => element.textContent === 'No');

  assert.ok(noTag);
  assert.match(noTag.className, /\binfo\b/);
  assert.equal(rendered.some((element) => element.textContent === 'Issue'), false);
});
