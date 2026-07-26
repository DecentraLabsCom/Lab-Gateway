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
    querySelector: () => null,
    contains: () => true,
    setAttribute: () => {},
    click: () => listeners.get('click')?.({ preventDefault() {} }),
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
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
    'timelineReservationId', 'loadTimelineBtn', 'timelineResult', 'upcomingReservationsList',
    'upcomingReservationsStatus', 'smtpSection',
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
    confirm: () => true,
    AuthTokenHandler: {
      showTokenModal: (...args) => promptCalls.push(args),
      getTokenConfigForPath: () => ({ key: 'billing', login: '/admin/login' }),
    },
  };
  const fetchCalls = [];
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
    fetch: (url, options = {}) => {
      fetchCalls.push({ url: String(url), options });
      return String(url) === '/billing/admin/notifications'
        ? billingResponse
        : Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    },
  });

  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager.js',
  });

  return { elements, promptCalls, fetchCalls };
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

test('cancellation click reads the reason from the reservation row and posts it', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
  });
  const reservationList = elements.get('upcomingReservationsList');
  const row = {
    dataset: { reservationKey: `0x${'ab'.repeat(32)}` },
    querySelector: (selector) => selector === '[data-reservation-reason]'
      ? { value: '1', disabled: false }
      : null,
  };
  const button = {
    disabled: false,
    closest: (selector) => {
      if (selector === '[data-action="cancel-reservation"]') return button;
      if (selector === '[data-reservation-key]') return button;
      if (selector === '.reservation-item') return row;
      return null;
    },
  };

  reservationList.dispatchEvent({ type: 'click', target: button });
  await new Promise((resolve) => setImmediate(resolve));

  const cancellation = fetchCalls.find(({ options }) => options.method === 'POST');
  assert.ok(cancellation);
  assert.match(cancellation.url, /\/lab-admin\/reservations\/0x[a-f0-9]{64}\/cancel$/);
  assert.deepEqual(JSON.parse(cancellation.options.body), { reasonCode: 1 });
});
