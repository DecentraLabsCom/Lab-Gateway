import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-resources.js', repoRoot);

function loadResources({ fetch = undefined } = {}) {
  const window = {};
  const context = vm.createContext({ window, fetch });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-publisher-resources.js',
  });
  return context.window.LabPublisherResources;
}

test('builds the detected resource inventory and deduplicates Guacamole connections', () => {
  const resources = loadResources();

  const inventory = resources.collectDetectedResources({
    hosts: {
      guacamoleUnmatched: [{ id: 7, name: 'unmatched' }],
      hosts: [
        {
          guacamole: {
            connections: [
              { id: 7, name: 'duplicate' },
              { id: 8, name: 'station' },
            ],
          },
        },
      ],
    },
    fmuInventory: [{ fileName: 'spring-damper.fmu' }],
  });

  assert.equal(JSON.stringify(inventory.fmus), JSON.stringify([{ fileName: 'spring-damper.fmu' }]));
  assert.equal(JSON.stringify(inventory.guacamole), JSON.stringify([
    { id: 7, name: 'unmatched' },
    { id: 8, name: 'station' },
  ]));
});

test('builds a reservation-independent FMU describe URL', () => {
  const resources = loadResources();

  assert.equal(
    resources.buildFmuDescribeUrl('https://gateway.example/fmu/', 'spring damper.fmu'),
    'https://gateway.example/fmu/api/v1/simulations/describe?fmuFileName=spring%20damper.fmu',
  );
});

test('fetches a provider describe token before requesting FMU metadata', async () => {
  const calls = [];
  const resources = loadResources({
    fetch: async (url, options) => {
      calls.push({ url: String(url), options });
      if (calls.length === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ token: 'describe-token' }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ fmiVersion: '3.0', modelVariables: [] }),
      };
    },
  });
  const signal = { aborted: false };

  const metadata = await resources.fetchFmuMetadata({
    fmuFileName: 'spring damper.fmu',
    gatewayUrl: 'https://gateway.example/fmu/',
    signal,
  });

  assert.deepEqual(metadata, { fmiVersion: '3.0', modelVariables: [] });
  assert.equal(calls[0].url, '/lab-admin/fmu/provider-describe-token');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[0].options.signal, signal);
  assert.equal(calls[0].options.body, JSON.stringify({ fmuFileName: 'spring damper.fmu' }));
  assert.equal(calls[1].url, 'https://gateway.example/fmu/api/v1/simulations/describe?fmuFileName=spring%20damper.fmu');
  assert.equal(calls[1].options.headers.Authorization, 'Bearer describe-token');
  assert.equal(calls[1].options.signal, signal);
});

test('reports provider token and describe failures with their public details', async () => {
  const resources = loadResources({
    fetch: async () => ({
      ok: false,
      status: 403,
      json: async () => ({ error: 'Provider access denied' }),
    }),
  });

  await assert.rejects(
    resources.fetchFmuMetadata({
      fmuFileName: 'spring.fmu',
      gatewayUrl: 'https://gateway.example/fmu',
      signal: { aborted: false },
    }),
    { message: 'Provider access denied' },
  );

  const describeFailure = loadResources({
    fetch: async (url) => {
      if (url === '/lab-admin/fmu/provider-describe-token') {
        return { ok: true, status: 200, json: async () => ({ token: 'token' }) };
      }
      return { ok: false, status: 502, json: async () => ({ error: 'Describe unavailable' }) };
    },
  });

  await assert.rejects(
    describeFailure.fetchFmuMetadata({
      fmuFileName: 'spring.fmu',
      gatewayUrl: 'https://gateway.example/fmu',
      signal: { aborted: false },
    }),
    { message: 'Describe unavailable' },
  );
});
