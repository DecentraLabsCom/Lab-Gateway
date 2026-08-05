import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const html = fs.readFileSync(new URL('blockchain-services/src/main/resources/static/wallet-dashboard/index.html', repoRoot), 'utf8');
const api = fs.readFileSync(new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/api.js', repoRoot), 'utf8');
const admin = fs.readFileSync(new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/admin.js', repoRoot), 'utf8');

test('settlement dashboard exposes the canonical claim workflow', () => {
  assert.match(html, /providerSettlementOperationSelect/);
  assert.match(html, /providerSettlementClaimIdInput/);
  assert.match(html, /providerSettlementBatchIdInput/);
  assert.match(html, /providerSettlementInvoiceIdInput/);
  assert.match(api, /submitProviderInvoice\(/);
  assert.match(api, /approveProviderInvoice\(/);
  assert.match(api, /recordProviderPayout\(/);
  assert.match(api, /\/billing\/provider-receivables/);
  assert.doesNotMatch(api, /transitionProviderReceivableState/);
  assert.match(admin, /API\.submitProviderInvoice\(/);
  assert.match(admin, /API\.approveProviderInvoice\(/);
  assert.match(admin, /API\.recordProviderPayout\(/);
});

test('settlement dashboard no longer submits the fail-closed generic transition', () => {
  const handler = admin.match(/async function handleProviderSettlementTransition[\s\S]*?\n}\n/);
  assert.ok(handler, 'canonical settlement handler should exist');
  assert.doesNotMatch(handler[0], /transitionProviderReceivableState/);
  assert.doesNotMatch(html, /value="2:3"/);
  assert.doesNotMatch(html, /value="3:4"/);
  assert.doesNotMatch(html, /value="4:5"/);
});
