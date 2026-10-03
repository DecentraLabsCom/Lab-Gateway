import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const sourcePath = new URL(
  'blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/access-policies.js',
  repoRoot,
);

function loadAttributesParser() {
  const window = {};
  const document = { addEventListener() {} };
  vm.runInNewContext(fs.readFileSync(sourcePath, 'utf8'), { window, document, console });
  return window.WalletDashboardAccessPolicyAttributes;
}

test('normalizes JSON attribute scalars to the backend list contract', () => {
  const parser = loadAttributesParser();

  assert.deepEqual(JSON.parse(JSON.stringify(parser.parse('{"schacHome":"Hola","affiliation":["student","staff"]}'))), {
    schacHome: ['Hola'],
    affiliation: ['student', 'staff'],
  });
});

test('reports a concise JSON format hint for matcher syntax', () => {
  const parser = loadAttributesParser();

  assert.throws(
    () => parser.parse('{schacHome="Hola"}'),
    /Use JSON syntax like \{\"schacHome\":\[\"Hola\"\]\}/,
  );
});

test('rejects arrays and nested attribute values', () => {
  const parser = loadAttributesParser();

  assert.throws(() => parser.parse('["student"]'), /JSON object/);
  assert.throws(() => parser.parse('{"profile":{"name":"student"}}'), /scalar values/);
});
