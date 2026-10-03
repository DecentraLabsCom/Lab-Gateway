import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const htmlPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/index.html', repoRoot);
const tabsScriptPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/wallet-dashboard-tabs.js', repoRoot);
const adminScriptPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/admin.js', repoRoot);

test('wallet dashboard exposes the three role-aware workflow tabs', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const expectedTabs = ['overview', 'institution', 'settlements'];

  assert.match(html, /role="tablist"/);
  for (const tab of expectedTabs) {
    assert.match(html, new RegExp(`data-wallet-tab="${tab}"`));
    assert.match(html, new RegExp(`aria-controls="wallet-panel-${tab}"`));
    assert.match(html, new RegExp(`id="wallet-panel-${tab}"[^>]*role="tabpanel"`));
    assert.match(html, new RegExp(`data-wallet-tab-section="${tab}"`));
  }

  assert.match(html, /id="accessPoliciesSection"[^>]*class="card hidden"/);
  assert.match(html, /Access Policies/);
  assert.match(html, /Coming Soon/);
});

test('wallet dashboard tab controller supports hashes, keyboard navigation and role visibility', () => {
  const source = fs.readFileSync(tabsScriptPath, 'utf8');
  const admin = fs.readFileSync(adminScriptPath, 'utf8');

  assert.match(source, /window\.location\.hash/);
  assert.match(source, /ArrowLeft/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /Home/);
  assert.match(source, /End/);
  assert.match(source, /setRoleVisibility/);
  assert.match(source, /wallet-dashboard:tab-activated/);
  assert.match(admin, /accessPoliciesSection/);
  assert.match(admin, /WalletDashboardTabs/);
});
