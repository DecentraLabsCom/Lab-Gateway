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

function loadLabManager({
  billingResponse,
  actionableResponse = null,
  labsResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ labs: [] }),
  }),
  powerPoliciesResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ policies: [] }),
  }),
}) {
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
    'guacamoleCandidateList', 'fmuSyncBtn', 'fmuSyncKey', 'fmuSyncLabSelect',
    'fmuSyncFile', 'fmuSyncResult', 'fmuSyncDescription', 'fmuSyncLicense',
    'fmuSyncDocsUrl', 'fmuSyncContactEmail', 'fmuSyncDescriptionHint',
    'fmuSyncLicenseHint', 'aasLinkKey', 'aasLinkLabSelect', 'aasLinkAasId',
    'aasLinkSaveBtn', 'aasLinkCheckBtn', 'aasLinkDeleteBtn', 'aasLinkResult',
    'timelineReservationId', 'loadTimelineBtn', 'timelineResult', 'upcomingReservationsList',
    'upcomingReservationsStatus', 'smtpSection',
    'graphSection', 'toast', 'labManagerAccessBadge', 'opsHint', 'activityFeedList',
    'refreshPowerControllersBtn', 'powerControllerList', 'powerControllersStatus',
    'powerControllersHint', 'powerOperationReason', 'powerCycleSeconds',
    'powerMaintenanceMode', 'refreshPowerPoliciesBtn', 'powerPolicySelect',
    'powerPolicyLabSelect', 'powerPolicyJson', 'formatPowerPolicyBtn',
    'savePowerPolicyBtn', 'powerPoliciesStatus', 'powerPolicyEditorHint',
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
      const parsedUrl = new URL(String(url), 'http://localhost');
      if (parsedUrl.pathname === '/lab-admin/reservations/actionable' && actionableResponse) {
        const response = typeof actionableResponse === 'function'
          ? actionableResponse(parsedUrl, fetchCalls.length)
          : actionableResponse;
        return Promise.resolve(response);
      }
      if (parsedUrl.pathname === '/lab-admin/labs') {
        return Promise.resolve(labsResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/policies' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerPoliciesResponse);
      }
      return parsedUrl.pathname === '/billing/admin/notifications'
        ? billingResponse
        : Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    },
  });

  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager.js',
  });

  return { elements, promptCalls, fetchCalls };
}

test('forwards the actionable reservation resume cursor when loading more', async () => {
  const cursor = 'djF8N3wxMDA';
  const actionableResponse = (url) => ({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      reservations: [],
      pagination: {
        offset: Number(url.searchParams.get('offset')),
        limit: 100,
        returned: 0,
        nextOffset: 100,
        hasMore: url.searchParams.get('cursor') === cursor,
        ...(url.searchParams.get('cursor') === null ? { nextCursor: cursor } : {}),
      },
    }),
  });
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    actionableResponse,
  });

  await new Promise((resolve) => setImmediate(resolve));
  const list = elements.get('upcomingReservationsList');
  const loadMoreButton = {
    closest: (selector) => selector === '[data-action="load-more-actionable"]' ? loadMoreButton : null,
  };
  list.dispatchEvent({ type: 'click', target: loadMoreButton });
  await new Promise((resolve) => setImmediate(resolve));

  const actionableCalls = fetchCalls
    .map(({ url }) => new URL(url, 'http://localhost'))
    .filter(({ pathname }) => pathname === '/lab-admin/reservations/actionable');
  assert.equal(actionableCalls.length, 2);
  assert.equal(actionableCalls[0].searchParams.get('cursor'), null);
  assert.equal(actionableCalls[1].searchParams.get('cursor'), cursor);
});

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

test('renders the provider service-failure action for an access-authorized reservation', async () => {
  const reservationKey = `0x${'cd'.repeat(32)}`;
  const { elements } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    actionableResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        count: 1,
        pagination: {
          offset: 0,
          limit: 100,
          returned: 1,
          total: 501,
          nextOffset: 1,
          hasMore: true,
        },
        reservations: [{
          reservationKey,
          status: 2,
          statusLabel: 'ACCESS_AUTHORIZED',
          cancellable: true,
          cancellationOptions: [{
            reasonCode: 8,
            label: 'Service failure',
            deadline: Math.floor(Date.now() / 1000) + 3600,
            reputationPenalty: -3,
          }],
          start: Math.floor(Date.now() / 1000) - 60,
          end: Math.floor(Date.now() / 1000) + 3600,
          labId: '42',
          priceCredits: '1',
          providerShareCredits: '0.9',
        }],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));

  const rendered = elements.get('upcomingReservationsList').innerHTML;
  assert.match(rendered, /Reason 8/);
  assert.match(rendered, /Report service failure/);
  assert.match(rendered, /data-action="cancel-reservation"/);
  assert.match(rendered, /data-action="load-more-actionable"/);
});

test('loads power policy lab options from provider labs and saves the selected lab', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    labsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '42', resourceType: 0, listed: true },
          { labId: '7', resourceType: 1, listed: false },
        ],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));

  const labSelect = elements.get('powerPolicyLabSelect');
  assert.deepEqual(
    labSelect.options.map((option) => option.value),
    ['42', '7'],
  );

  labSelect.value = '42';
  elements.get('powerPolicyJson').value = JSON.stringify({
    policyName: 'PLC policy',
    enabled: true,
    steps: [],
  });
  elements.get('savePowerPolicyBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'PUT' && url === '/ops/api/power/policies/42');
  assert.ok(saveCall);
  assert.equal(JSON.parse(saveCall.options.body).labId, '42');
});

test('loads FMU lab options and sends the selected lab as the AAS override', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    labsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '42', resourceType: 0, listed: true },
          { labId: '7', resourceType: 1, accessKey: 'spring-damper.fmu', listed: false },
        ],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(
    elements.get('fmuSyncKey').options.map((option) => option.value),
    ['spring-damper.fmu'],
  );
  const labSelect = elements.get('fmuSyncLabSelect');
  assert.deepEqual(
    labSelect.options.map((option) => option.value),
    ['7'],
  );

  labSelect.value = '7';
  elements.get('fmuSyncKey').value = 'spring-damper.fmu';
  elements.get('fmuSyncBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const syncCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url.startsWith('/aas-admin/fmu/spring-damper.fmu/sync?'));
  assert.ok(syncCall);
  assert.equal(new URLSearchParams(syncCall.url.split('?')[1]).get('labId'), '7');
});

test('loads AAS link FMU options and sends the selected lab when saving a link', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    labsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        labs: [
          { labId: '42', resourceType: 0, listed: true },
          { labId: '7', resourceType: 1, listed: false },
        ],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));

  const labSelect = elements.get('aasLinkLabSelect');
  assert.deepEqual(
    labSelect.options.map((option) => option.value),
    ['7'],
  );

  labSelect.value = '7';
  elements.get('aasLinkKey').value = 'spring-damper.fmu';
  elements.get('aasLinkAasId').value = 'urn:example:aas:spring-damper';
  elements.get('aasLinkSaveBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const linkCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url === '/aas-admin/fmu/spring-damper.fmu/aas-link');
  assert.ok(linkCall);
  assert.equal(JSON.parse(linkCall.options.body).labId, '7');
});
