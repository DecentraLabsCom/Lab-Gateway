import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  const classes = new Set();
  const element = {
    id,
    value: '',
    checked: false,
    hidden: false,
    textContent: '',
    innerHTML: '',
    style: {},
    options: [],
    files: [],
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      toggle: (name, force) => {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
      contains: (name) => classes.has(name),
    },
    addEventListener: (type, handler) => listeners.set(type, handler),
    appendChild: (child) => {
      if (Array.isArray(element.options)) element.options.push(child);
      return child;
    },
    querySelectorAll: () => [],
    setAttribute: () => {},
    click: () => listeners.get('click')?.({ preventDefault() {} }),
  };
  return element;
}

function loadLabManager({ billingResponse }) {
  const ids = [
    'driver', 'enabled', 'from', 'fromName', 'defaultTo', 'timezone',
    'smtpHost', 'smtpPort', 'smtpUser', 'smtpPass', 'smtpStartTls',
    'graphTenant', 'graphClientId', 'graphClientSecret', 'graphFrom',
    'driverSummary', 'configStatus', 'configModal', 'configureBtn',
    'closeModal', 'cancelModal', 'provisionHostModal', 'closeProvisionHostModal',
    'cancelProvisionHost', 'saveProvisionHost', 'winrmCredentialsModal',
    'closeWinrmCredentialsModal', 'cancelWinrmCredentials', 'saveWinrmCredentials',
    'winrmCredentialRef', 'winrmCredentialAddress', 'winrmCredentialUser',
    'winrmCredentialPassword', 'provisionConnectionId', 'provisionHostName',
    'provisionHostNameCandidates', 'provisionHostAddress', 'provisionHostMac',
    'provisionHostLabs', 'provisionHostLabsSummary', 'provisionHeartbeatPath',
    'btnTestLoad', 'saveConfigBtn', 'btnTestEmail', 'refreshHostsBtn', 'hostList',
    'guacamoleCandidateList', 'fmuSyncBtn', 'fmuSyncKey', 'fmuSyncLabId',
    'fmuSyncFile', 'fmuSyncResult', 'fmuSyncDescription', 'fmuSyncLicense',
    'fmuSyncDocsUrl', 'fmuSyncContactEmail', 'fmuSyncDescriptionHint',
    'fmuSyncLicenseHint', 'aasLinkKey', 'aasLinkLabId', 'aasLinkAasId',
    'aasLinkSaveBtn', 'aasLinkCheckBtn', 'aasLinkDeleteBtn', 'aasLinkResult',
    'timelineReservationId', 'loadTimelineBtn', 'timelineResult', 'smtpSection',
    'graphSection', 'toast', 'labManagerAccessBadge', 'opsHint', 'activityFeedList',
  ];
  const elements = new Map(ids.map((id) => [id, createElement(id)]));
  const document = {
    addEventListener: (type, handler) => {
      if (type === 'DOMContentLoaded') handler();
    },
    querySelector: (selector) => selector.startsWith('#')
      ? elements.get(selector.slice(1))
      : createElement(selector),
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: () => [],
    createElement: () => createElement('created'),
  };
  const promptCalls = [];
  const window = {
    AuthTokenHandler: {
      showTokenModal: (...args) => promptCalls.push(args),
      getTokenConfigForPath: () => ({ key: 'billing', login: '/admin/login' }),
    },
  };
  const context = vm.createContext({
    document,
    window,
    console,
    Intl,
    URLSearchParams,
    URL,
    Promise,
    setTimeout,
    clearTimeout,
    Option: function Option(text, value) {
      this.textContent = text;
      this.value = value;
    },
    fetch: (url) => String(url) === '/billing/admin/notifications'
      ? billingResponse
      : Promise.resolve({ ok: true, status: 200, json: async () => ({}) }),
  });

  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager.js',
  });

  return { elements, promptCalls };
}

test('reuses an existing billing session while the initial notifications check is pending', async () => {
  let resolveBilling;
  const billingResponse = new Promise((resolve) => {
    resolveBilling = resolve;
  });
  const { elements, promptCalls } = loadLabManager({ billingResponse });

  elements.get('configureBtn').click();
  assert.equal(promptCalls.length, 0);

  resolveBilling({
    ok: true,
    status: 200,
    json: async () => ({ config: {} }),
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(promptCalls.length, 0);
  assert.equal(elements.get('configModal').classList.contains('show'), true);
});
