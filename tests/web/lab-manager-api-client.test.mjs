import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/core/api-client.js', repoRoot);

function loadApiClient() {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'api-client.js',
  });
  return context.window.LabManagerApiClient;
}

test('preserves request options and returns JSON responses', async () => {
  const apiClientModule = loadApiClient();
  const calls = [];
  const client = apiClientModule.createClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ operations: [] }) };
    },
  });

  const body = await client.requestJson('/ops/api/operations/recent?limit=8', {
    credentials: 'include',
    skipAuthPrompt: true,
  });

  assert.deepEqual(body, { operations: [] });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/ops/api/operations/recent?limit=8');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[0].options.skipAuthPrompt, true);
});

test('reports the HTTP status when a JSON request fails', async () => {
  const apiClientModule = loadApiClient();
  const client = apiClientModule.createClient({
    fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }),
  });

  await assert.rejects(
    client.requestJson('/ops/api/operations/recent'),
    { message: 'HTTP 503' },
  );
});
