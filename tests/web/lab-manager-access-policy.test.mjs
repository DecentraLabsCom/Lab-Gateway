import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-access-policy.js', repoRoot);

function createBadge() {
  const classes = new Set(['local', 'private', 'external', 'token-required-action']);
  return {
    textContent: '',
    title: 'old title',
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
    },
  };
}

function loadAccessPolicyController({ badge, fetchImpl }) {
  const document = {
    querySelector(selector) {
      assert.equal(selector, '#labManagerAccessBadge');
      return badge;
    },
  };
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-access-policy.js',
  });

  return window.LabManagerAccessPolicy.createController({ document, fetchImpl });
}

test('renders access policy badge states without changing class semantics', () => {
  const externalBadge = createBadge();
  const externalController = loadAccessPolicyController({
    badge: externalBadge,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  });
  externalController.updateAccessPolicyBadge({ dashboardLocalOnly: false });
  assert.equal(externalBadge.textContent, 'External Access Allowed');
  assert.equal(externalBadge.classList.contains('external'), true);
  assert.equal(externalBadge.classList.contains('local'), false);

  const cidrBadge = createBadge();
  const cidrController = loadAccessPolicyController({
    badge: cidrBadge,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  });
  cidrController.updateAccessPolicyBadge({
    dashboardLocalOnly: true,
    allowPrivateNetworks: true,
    dashboardAllowPrivate: true,
    dashboardAllowedCidrs: '10.0.0.0/8, 192.168.0.0/16',
  });
  assert.equal(cidrBadge.textContent, 'Private CIDR Allowlist');
  assert.equal(cidrBadge.title, '10.0.0.0/8, 192.168.0.0/16');
  assert.equal(cidrBadge.classList.contains('private'), true);

  const localBadge = createBadge();
  const localController = loadAccessPolicyController({
    badge: localBadge,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  });
  localController.updateAccessPolicyBadge({});
  assert.equal(localBadge.textContent, 'Localhost Only');
  assert.equal(localBadge.classList.contains('local'), true);
});

test('loads access policy with the existing session options and handles protected failures', async () => {
  const calls = [];
  const cases = [
    { status: 401, text: 'Lab Manager session required' },
    { status: 403, text: 'Access Policy Blocked' },
    { status: 503, text: 'Access Policy Unavailable' },
  ];

  for (const policyCase of cases) {
    const badge = createBadge();
    const controller = loadAccessPolicyController({
      badge,
      fetchImpl: async (url, options) => {
        calls.push({ url, options });
        return {
          ok: false,
          status: policyCase.status,
          json: async () => ({}),
        };
      },
    });

    await controller.loadAccessPolicy();
    assert.equal(badge.textContent, policyCase.text);
    assert.equal(badge.classList.contains('local'), false);
    assert.equal(badge.classList.contains('private'), false);
    assert.equal(badge.classList.contains('external'), false);
    assert.equal(badge.classList.contains('token-required-action'), false);
  }

  assert.equal(calls.length, cases.length);
  calls.forEach(({ url, options }) => {
    assert.equal(url, '/lab-manager/access-policy');
    assert.equal(options.credentials, 'include');
    assert.equal(options.skipAuthPrompt, true);
  });
});
