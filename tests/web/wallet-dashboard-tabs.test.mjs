import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const htmlPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/index.html', repoRoot);
const tabsScriptPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/wallet-dashboard-tabs.js', repoRoot);
const adminScriptPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/admin.js', repoRoot);
const accessPoliciesScriptPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/js/access-policies.js', repoRoot);
const policyStylesPath = new URL('blockchain-services/src/main/resources/static/wallet-dashboard/assets/css/wallet-dashboard-policy.css', repoRoot);

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

  assert.match(html, /id="accessPoliciesSection"[^>]*class="card"/);
  assert.match(html, /id="accessPolicyForm"/);
  assert.match(html, /id="accessPolicyActivateBtn"/);
  assert.match(html, /data-wallet-tab="institution"[\s\S]*Institutional Policies/);
  assert.match(html, /id="creditPolicyTitle">Spending Policy<\/h2>/);
  assert.match(html, /fa-shield-halved[\s\S]*> Access Policy<\/h2>/);
  assert.match(html, /id="gatewayHomeLink"[^>]*href="\/"/);
  assert.match(html, /src="assets\/images\/LogoBannerDLabs\.png"/);
    assert.match(html, /<div class="logo">\s*<a[\s\S]*gatewayHomeLink[\s\S]*<\/a>\s*<\/div>\s*<h1 class="logo-title">Wallet &amp; Billing<\/h1>/);
  assert.match(html, /id="accessPolicyTestCategories"[^>]*data-policy-multiselect/);
  assert.doesNotMatch(html, /<select id="accessPolicyTestCategories"[^>]*multiple/);
  assert.match(html, /Price \(raw units\)/);
  assert.doesNotMatch(html, /Institution &amp; Credits/);
  assert.doesNotMatch(html, /Access Policies/);
  assert.doesNotMatch(html, /Coming Soon/);
});

test('wallet dashboard tab controller supports hashes, keyboard navigation and role visibility', () => {
  const source = fs.readFileSync(tabsScriptPath, 'utf8');
  const admin = fs.readFileSync(adminScriptPath, 'utf8');
  const accessPolicies = fs.readFileSync(accessPoliciesScriptPath, 'utf8');
  const policyStyles = fs.readFileSync(policyStylesPath, 'utf8');

  assert.match(source, /window\.location\.hash/);
  assert.match(source, /ArrowLeft/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /Home/);
  assert.match(source, /End/);
  assert.match(source, /setRoleVisibility/);
  assert.match(source, /wallet-dashboard:tab-activated/);
  assert.match(admin, /accessPoliciesSection/);
  assert.match(admin, /WalletDashboardTabs/);
  assert.match(admin, /creditPolicyTitle\.textContent = 'Spending Policy and Operator Controls'/);
  assert.match(admin, /creditPolicyTitle\.textContent = 'Spending Policy'/);
  assert.doesNotMatch(admin, /creditPolicyTitle\.textContent = 'Institution Policy/);
  assert.match(accessPolicies, /data-multiselect-option/);
  assert.match(accessPolicies, /categories: selectedValues\(\$\('accessPolicyTestCategories'\)\)/);
  assert.doesNotMatch(accessPolicies, /accessPolicyTestCategories'\)\.value\.split\(','\)/);
  assert.doesNotMatch(accessPolicies, /fa-search/);
  assert.match(policyStyles, /\.policy-multi-select-trigger \{[\s\S]*padding: var\(--spacing-sm\);/);
  assert.doesNotMatch(policyStyles, /\.policy-multi-select-trigger \{[\s\S]*min-height: 2\.8rem;/);
  assert.doesNotMatch(policyStyles, /\.policy-multi-select-search input \{[\s\S]*padding: [^;]*2rem;/);
});

test('settlement payout action stays with the lab selector before the metrics column', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const selectorStart = html.indexOf('<div class="form-group collect-select-group">');
  const payoutStart = html.indexOf('<div class="collect-actions" id="providerPayoutActions">');
  const metricsStart = html.indexOf('<div id="collectStatusMetrics"');

  assert.ok(selectorStart >= 0, 'settlement lab selector should exist');
  assert.ok(payoutStart > selectorStart, 'payout action should follow the lab selector');
  assert.ok(metricsStart > payoutStart, 'metrics should remain after the selector/action column');
  assert.match(html, /id="collectLabBtn"[^>]*>\s*<i class="fas fa-coins"><\/i> Request Payout/);
});
