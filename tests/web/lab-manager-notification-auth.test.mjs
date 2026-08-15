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
    disabled: false,
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
    removeAttribute: () => {},
    click: () => listeners.get('click')?.({ preventDefault() {} }),
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
  };
  return element;
}

function loadLabManager({
  billingResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ config: {} }),
  }),
  activeTabs = ['operations', 'energy', 'digital-twins'],
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
  powerControllersResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ controllers: [] }),
  }),
  powerCredentialsResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ credentials: [] }),
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
    'powerControllerSelect', 'powerControllerId', 'powerControllerName',
    'powerControllerDriver', 'powerControllerEnabled', 'powerControllerHost',
    'powerControllerPort', 'powerControllerCredentialRef', 'powerControllerProfile',
    'powerControllerSnmpVersion', 'powerControllerTimeoutSeconds',
    'powerControllerRetries', 'powerControllerOutlets', 'addPowerControllerOutletBtn',
    'powerControllerNetioPath', 'powerControllerNetioHttps', 'powerControllerNetioVerifyTls',
    'savePowerControllerBtn', 'powerControllerEditorHint',
    'refreshPowerCredentialsBtn', 'powerCredentialsList', 'powerCredentialsStatus',
    'powerCredentialsHint', 'powerCredentialSelect', 'powerCredentialRef',
    'powerCredentialType', 'powerCredentialUsername', 'powerCredentialPassword',
    'powerCredentialCommunity', 'powerCredentialAuthProtocol', 'powerCredentialAuthPassword',
    'powerCredentialPrivProtocol', 'powerCredentialPrivPassword', 'powerCredentialContextName',
    'powerCredentialSaveBtn', 'powerCredentialEditorHint',
    'powerMaintenanceMode', 'powerPolicySelect', 'powerPolicyLabSelect',
    'powerPolicyName', 'powerPolicyEnabled', 'powerPolicyRespectLocalMode',
    'powerPolicyMaintenanceMode', 'powerPolicyStartFailureMode',
    'powerPolicyEndFailureMode', 'powerPolicySteps', 'addPowerPolicyStepBtn',
    'savePowerPolicyBtn', 'powerPoliciesStatus', 'powerPolicyEditorHint',
    'notificationsAccessGate', 'notificationsConfigContent', 'unlockNotificationsBtn',
    'smtpPasswordHint', 'graphClientSecretHint',
  ];
  const elements = new Map(ids.map((id) => [id, createElement(id)]));
  const documentListeners = new Map();
  const document = {
    addEventListener: (type, handler) => {
      if (type === 'DOMContentLoaded') {
        handler();
        return;
      }
      const handlers = documentListeners.get(type) || [];
      handlers.push(handler);
      documentListeners.set(type, handlers);
    },
    dispatchEvent: (event) => {
      (documentListeners.get(event.type) || []).forEach((handler) => handler(event));
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
      if (parsedUrl.pathname === '/ops/api/power/controllers' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerControllersResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/credentials' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerCredentialsResponse);
      }
      return parsedUrl.pathname === '/billing/admin/notifications'
        ? billingResponse
        : Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    },
  });

  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager.js',
  });

  const activateTab = (tab) => document.dispatchEvent({
    type: 'lab-manager:tab-activated',
    detail: { tab, firstActivation: true },
  });
  activeTabs.forEach(activateTab);

  return { elements, promptCalls, fetchCalls, activateTab };
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

test('reuses the existing Lab Manager session without prompting on Operations entry', async () => {
  const { fetchCalls } = loadLabManager({});

  await new Promise((resolve) => setImmediate(resolve));

  const accessPolicyCall = fetchCalls.find(({ url, options }) => (
    String(url) === '/lab-manager/access-policy' && options.cache === 'no-store'
  ));
  assert.ok(accessPolicyCall, 'Operations should refresh the existing Lab Manager session before loading data');
  assert.equal(accessPolicyCall.options.credentials, 'same-origin');
  assert.equal(accessPolicyCall.options.skipAuthPrompt, true);

  const activityCall = fetchCalls.find(({ url }) => String(url).startsWith('/ops/api/operations/recent'));
  assert.ok(activityCall, 'Recent Operations should be loaded when Operations is activated');
  assert.equal(activityCall.options.credentials, 'include');
  assert.equal(activityCall.options.skipAuthPrompt, true);

  const actionableCall = fetchCalls.find(({ url }) => String(url).startsWith('/lab-admin/reservations/actionable'));
  assert.ok(actionableCall, 'Actionable Reservations should be loaded when Operations is activated');
  assert.equal(actionableCall.options.credentials, 'include');
  assert.equal(actionableCall.options.skipAuthPrompt, true);
});

test('reserves a tall, explicit scroll area for actionable reservation details', () => {
  const stylesheet = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(
    stylesheet,
    /\.reservation-card \.reservation-list\s*\{[\s\S]*min-height:\s*520px;[\s\S]*height:\s*520px;[\s\S]*overflow-y:\s*auto;/,
  );
  assert.match(
    stylesheet,
    /@media \(min-width: 701px\)[\s\S]*\.reservation-card \.reservation-list\s*\{[\s\S]*min-height:\s*720px;[\s\S]*height:\s*720px;[\s\S]*max-height:\s*720px;/,
  );
});

test('does not request or prompt for billing access until Notifications is opened', async () => {
  const { fetchCalls, promptCalls, activateTab } = loadLabManager({
    activeTabs: [],
    billingResponse: Promise.resolve({
      ok: false,
      status: 401,
      json: async () => ({}),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fetchCalls.some(({ url }) => url === '/billing/admin/notifications'), false);
  assert.equal(promptCalls.length, 0);

  activateTab('energy');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fetchCalls.some(({ url }) => url === '/billing/admin/notifications'), false);

  activateTab('notifications');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fetchCalls.filter(({ url }) => url === '/billing/admin/notifications').length, 1);
  assert.equal(promptCalls.length, 1);
});

test('reuses an existing billing session while the Notifications access check is pending', async () => {
  let resolveBilling;
  const billingResponse = new Promise((resolve) => {
    resolveBilling = resolve;
  });
  const { elements, promptCalls, activateTab } = loadLabManager({
    billingResponse,
    activeTabs: [],
  });

  activateTab('notifications');

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

test('omits blank notification secrets when saving an existing configuration', async () => {
  const { elements, fetchCalls } = loadLabManager({
    activeTabs: ['notifications'],
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        config: {
          smtp: { passwordConfigured: true },
          graph: { clientSecretConfigured: true },
        },
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('smtpPass').value = '';
  elements.get('graphClientSecret').value = '   ';
  elements.get('saveConfigBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    url === '/billing/admin/notifications' && options.method === 'POST');
  assert.ok(saveCall);
  const body = JSON.parse(saveCall.options.body);
  assert.equal(Object.hasOwn(body.smtp, 'password'), false);
  assert.equal(Object.hasOwn(body.graph, 'clientSecret'), false);
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
    powerControllersResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        controllers: [{
          id: 'pdu-1',
          name: 'Bench PDU',
          outlets: [{ outlet: '1', displayName: 'Bench outlet' }],
        }],
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
  elements.get('powerPolicyName').value = 'PLC policy';
  elements.get('powerPolicyEnabled').checked = true;
  elements.get('powerPolicyRespectLocalMode').checked = true;
  elements.get('powerPolicyMaintenanceMode').checked = false;
  elements.get('powerPolicyStartFailureMode').value = 'fail_reservation_start';
  elements.get('powerPolicyEndFailureMode').value = 'warn_and_continue';
  elements.get('addPowerPolicyStepBtn').click();
  assert.match(elements.get('powerPolicySteps').innerHTML, /data-step-field="controllerId"/);
  elements.get('savePowerPolicyBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'PUT' && url === '/ops/api/power/policies/42');
  assert.ok(saveCall);
  assert.deepEqual(JSON.parse(saveCall.options.body), {
    labId: '42',
    policyName: 'PLC policy',
    enabled: true,
    respectLocalMode: true,
    maintenanceMode: false,
    startFailureMode: 'fail_reservation_start',
    endFailureMode: 'warn_and_continue',
    steps: [{
      phase: 'pre_start',
      sequence: 10,
      controllerId: 'pdu-1',
      outlet: '1',
      action: 'on',
      required: true,
      readBackRequired: true,
      offSeconds: 10,
      delayBeforeSeconds: 0,
      delayAfterSeconds: 0,
      timeoutSeconds: 20,
      retryCount: 0,
      allowProtected: false,
      conditions: {},
      desiredState: 'on',
    }],
  });
});

test('loads an existing power policy into the visual editor fields', async () => {
  const { elements } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    powerPoliciesResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ policies: [{
        labId: '42',
        policyName: 'Existing policy',
        enabled: false,
        respectLocalMode: false,
        maintenanceMode: true,
        startFailureMode: 'warn_and_continue',
        endFailureMode: 'fail_reservation_start',
        steps: [{
          phase: 'post_start',
          sequence: 20,
          controllerId: 'pdu-1',
          outlet: '1',
          action: 'cycle',
          offSeconds: 30,
          conditions: { after: 'boot' },
        }],
      }] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerPolicySelect').value = '42';
  elements.get('powerPolicySelect').dispatchEvent({ type: 'change' });

  assert.equal(elements.get('powerPolicyName').value, 'Existing policy');
  assert.equal(elements.get('powerPolicyEnabled').checked, false);
  assert.equal(elements.get('powerPolicyRespectLocalMode').checked, false);
  assert.equal(elements.get('powerPolicyMaintenanceMode').checked, true);
  assert.equal(elements.get('powerPolicyStartFailureMode').value, 'warn_and_continue');
  assert.equal(elements.get('powerPolicyEndFailureMode').value, 'fail_reservation_start');
  assert.match(elements.get('powerPolicySteps').innerHTML, /post_start/);
  assert.doesNotMatch(fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8'), /id="refreshPowerPoliciesBtn"/);
});

test('creates a provider-local power controller from the controller form', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerControllerId').value = 'pdu-lab-01';
  elements.get('powerControllerName').value = 'Bench PDU';
  elements.get('powerControllerDriver').value = 'mock';
  elements.get('powerControllerEnabled').checked = true;
  elements.get('powerControllerHost').value = '';
  elements.get('powerControllerPort').value = '161';
  elements.get('powerControllerProfile').value = 'auto';
  elements.get('powerControllerSnmpVersion').value = 'v2c';
  elements.get('powerControllerTimeoutSeconds').value = '3';
  elements.get('powerControllerRetries').value = '1';
  elements.get('savePowerControllerBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url === '/ops/api/power/controllers');
  assert.ok(saveCall);
  assert.deepEqual(JSON.parse(saveCall.options.body), {
    id: 'pdu-lab-01',
    name: 'Bench PDU',
    driver: 'mock',
    enabled: true,
    host: '',
    port: 161,
    credentialRef: '',
    config: {
      profile: 'auto',
      snmpVersion: 'v2c',
      timeoutSeconds: 3,
      retries: 1,
    },
    outlets: [{
      outlet: '1',
      displayName: '',
      logicalName: '',
      protected: false,
      critical: false,
      defaultState: 'off',
    }],
  });
});

test('creates a NETIO JSON power controller with its HTTP API settings', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerControllerId').value = 'netio-lab-01';
  elements.get('powerControllerName').value = 'NETIO Lab 01';
  elements.get('powerControllerDriver').value = 'netio-json';
  elements.get('powerControllerHost').value = '192.0.2.10';
  elements.get('powerControllerPort').value = '443';
  elements.get('powerControllerCredentialRef').value = 'netio-lab-01-http';
  elements.get('powerControllerNetioPath').value = '/netio.json';
  elements.get('powerControllerNetioHttps').checked = true;
  elements.get('powerControllerTimeoutSeconds').value = '4';
  elements.get('powerControllerRetries').value = '2';
  elements.get('savePowerControllerBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url === '/ops/api/power/controllers');
  assert.ok(saveCall);
  assert.deepEqual(JSON.parse(saveCall.options.body), {
    id: 'netio-lab-01',
    name: 'NETIO Lab 01',
    driver: 'netio-json',
    enabled: true,
    host: '192.0.2.10',
    port: 443,
    credentialRef: 'netio-lab-01-http',
    config: {
      path: '/netio.json',
      useHttps: true,
      verifyTls: true,
      timeoutSeconds: 4,
      retries: 2,
    },
    outlets: [{
      outlet: '1',
      displayName: '',
      logicalName: '',
      protected: false,
      critical: false,
      defaultState: 'off',
    }],
  });
});

test('creates a NETIO power credential without exposing its password', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerCredentialRef').value = 'netio-lab-01-http';
  elements.get('powerCredentialType').value = 'netio-http-basic';
  elements.get('powerCredentialUsername').value = 'netio-api';
  elements.get('powerCredentialPassword').value = 'secret-from-form';
  elements.get('powerCredentialSaveBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url === '/ops/api/power/credentials');
  assert.ok(saveCall);
  assert.deepEqual(JSON.parse(saveCall.options.body), {
    credentialRef: 'netio-lab-01-http',
    type: 'netio-http-basic',
    credentials: { username: 'netio-api', password: 'secret-from-form' },
    overwrite: false,
  });
});

test('loads an existing power credential and submits a replacement with overwrite', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    powerCredentialsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ credentials: [{
        credentialRef: 'netio-lab-01-http',
        type: 'netio-http-basic',
      }] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerCredentialSelect').value = 'netio-lab-01-http';
  elements.get('powerCredentialSelect').dispatchEvent({ type: 'change' });
  assert.equal(elements.get('powerCredentialRef').value, 'netio-lab-01-http');
  assert.equal(elements.get('powerCredentialRef').disabled, true);
  elements.get('powerCredentialUsername').value = 'netio-api';
  elements.get('powerCredentialPassword').value = 'rotated-secret';
  elements.get('powerCredentialSaveBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'POST' && url === '/ops/api/power/credentials');
  assert.ok(saveCall);
  assert.equal(JSON.parse(saveCall.options.body).overwrite, true);
});

test('loads an existing power controller and saves it through the update endpoint', async () => {
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    powerControllersResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ controllers: [{
        id: 'pdu-lab-01',
        name: 'Bench PDU',
        driver: 'mock',
        enabled: true,
        host: '',
        port: 161,
        credentialRef: '',
        config: { profile: 'auto', timeoutSeconds: 2, retries: 1 },
        outlets: [{ outlet: '1', logicalName: 'PLC', protected: true }],
      }] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerControllerSelect').value = 'pdu-lab-01';
  elements.get('powerControllerSelect').dispatchEvent({ type: 'change' });
  assert.equal(elements.get('powerControllerId').value, 'pdu-lab-01');
  assert.equal(elements.get('powerControllerId').disabled, true);
  assert.equal(elements.get('powerControllerName').value, 'Bench PDU');
  assert.match(elements.get('powerControllerOutlets').innerHTML, /PLC/);

  elements.get('powerControllerName').value = 'Bench PDU Updated';
  elements.get('savePowerControllerBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const saveCall = fetchCalls.find(({ url, options }) =>
    options.method === 'PUT' && url === '/ops/api/power/controllers/pdu-lab-01');
  assert.ok(saveCall);
  assert.equal(JSON.parse(saveCall.options.body).name, 'Bench PDU Updated');
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
