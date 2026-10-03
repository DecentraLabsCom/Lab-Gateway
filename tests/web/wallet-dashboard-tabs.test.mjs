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
  assert.match(html, /<textarea id="accessPolicyTestAttributes"[^>]*class="policy-json-preview"/);
  assert.match(html, /id="accessPolicyTestAttributes"[^>]*readonly[^>]*aria-haspopup="dialog"/);
  assert.match(html, /id="accessPolicyTestAttributes"[^>]*rows="1"/);
  assert.match(html, /id="accessPolicyAttributesModal"[^>]*role="dialog"[^>]*aria-modal="true"/);
  assert.match(html, /id="accessPolicyAttributesEditor"[^>]*class="policy-json-editor"/);
  assert.match(html, /id="applyAccessPolicyAttributesBtn"/);
  assert.match(html, /<textarea id="accessPolicyTransfer"[^>]*class="policy-transfer hidden"[^>]*rows="5"/);
  assert.match(html, /class="policy-form-action"[\s\S]*Save policy/);
  assert.match(html, /class="policy-form-action"[\s\S]*> Test/);
  assert.doesNotMatch(html, /id="accessPolicyTestPrice"/);
  assert.doesNotMatch(html, /Price \(raw units\)/);
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
  assert.match(accessPolicies, /data-remove-matcher/);
  assert.match(accessPolicies, /delete matchers\[key\]/);
  assert.match(accessPolicies, /categories: selectedValues\(\$\('accessPolicyTestCategories'\)\)/);
  assert.match(accessPolicies, /price: ['"]1['"]/);
  assert.match(accessPolicies, /accessPolicyAttributesModal/);
  assert.match(accessPolicies, /JSON\.parse/);
  assert.match(accessPolicies, /applyAccessPolicyAttributes/);
  assert.doesNotMatch(accessPolicies, /accessPolicyTestPrice/);
  assert.doesNotMatch(accessPolicies, /accessPolicyTestCategories'\)\.value\.split\(','\)/);
  assert.doesNotMatch(accessPolicies, /fa-search/);
  assert.match(policyStyles, /\.policy-multi-select-trigger \{[\s\S]*height: 3\.125rem;/);
  assert.doesNotMatch(policyStyles, /\.policy-multi-select-trigger \{[\s\S]*min-height: 2\.8rem;/);
  assert.doesNotMatch(policyStyles, /\.policy-multi-select-search input \{[\s\S]*padding: [^;]*2rem;/);
  assert.match(policyStyles, /\.policy-group-heading input,\s*\.policy-matcher-row input\s*\{[\s\S]*background: var\(--bg-primary\);[\s\S]*padding: var\(--spacing-sm\);/);
  assert.match(policyStyles, /\.policy-group-heading input:focus,\s*\.policy-matcher-row input:focus\s*\{/);
  assert.match(policyStyles, /\.policy-chip-remove\s*\{[\s\S]*cursor: pointer;/);
  assert.match(policyStyles, /\.policy-transfer,\s*\.policy-json-preview\s*\{[\s\S]*padding: 0\.5rem 0\.75rem;[\s\S]*background: var\(--bg-primary\);[\s\S]*font-family: monospace;/);
  assert.match(policyStyles, /\.policy-transfer\s*\{[\s\S]*resize: vertical;/);
  assert.match(policyStyles, /\.policy-transfer:focus,\s*\.policy-json-preview:focus\s*\{/);
  assert.match(policyStyles, /\.policy-transfer,\s*\.policy-json-preview\s*\{[\s\S]*background: var\(--bg-primary\);[\s\S]*font-family: monospace;/);
  assert.match(policyStyles, /\.policy-json-preview\s*\{[\s\S]*height: 3\.125rem;[\s\S]*min-height: 3\.125rem;[\s\S]*max-height: 3\.125rem;[\s\S]*resize: none;/);
  assert.match(policyStyles, /\.policy-json-preview:hover/);
  assert.match(policyStyles, /\.policy-json-modal \.modal-content/);
  assert.match(policyStyles, /\.policy-json-editor\s*\{[\s\S]*resize: vertical;/);
  assert.match(policyStyles, /\.policy-test-form \{ grid-template-columns: 1\.5fr 1fr auto; \}/);
  assert.match(policyStyles, /\.policy-form-action\s*\{[\s\S]*align-self: stretch;[\s\S]*align-items: center;[\s\S]*justify-content: center;[\s\S]*padding-top: calc\(1\.44rem \+ var\(--spacing-xs\)\);/);
  assert.match(policyStyles, /\.policy-form-action \.btn\s*\{[\s\S]*display: inline-flex;[\s\S]*align-items: center;[\s\S]*justify-content: center;[\s\S]*gap: 0\.5rem;/);
  assert.doesNotMatch(policyStyles, /\.policy-form-action\s*\{[^}]*min-height: 3\.125rem;/);
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
