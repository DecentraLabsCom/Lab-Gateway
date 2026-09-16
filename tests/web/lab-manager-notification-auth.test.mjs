import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager.js', repoRoot);
const stateScriptPath = new URL('web/assets/js/core/state.js', repoRoot);
const apiClientScriptPath = new URL('web/assets/js/core/api-client.js', repoRoot);
const activityScriptPath = new URL('web/assets/js/lab-manager-activity.js', repoRoot);
const accessPolicyScriptPath = new URL('web/assets/js/lab-manager-access-policy.js', repoRoot);
const heartbeatErrorsScriptPath = new URL('web/assets/js/lab-manager-heartbeat-errors.js', repoRoot);
const hostsScriptPath = new URL('web/assets/js/lab-manager-hosts.js', repoRoot);
const hostRenderersScriptPath = new URL('web/assets/js/lab-manager-host-renderers.js', repoRoot);
const hostDiscoveryScriptPath = new URL('web/assets/js/lab-manager-host-discovery.js', repoRoot);
const winrmCredentialsScriptPath = new URL('web/assets/js/lab-manager-winrm-credentials.js', repoRoot);
const winrmTrustScriptPath = new URL('web/assets/js/lab-manager-winrm-trust.js', repoRoot);
const winrmTrustModalScriptPath = new URL('web/assets/js/lab-manager-winrm-trust-modal.js', repoRoot);
const hostProvisioningScriptPath = new URL('web/assets/js/lab-manager-host-provisioning.js', repoRoot);
const hostModalsScriptPath = new URL('web/assets/js/lab-manager-host-modals.js', repoRoot);
const hostViewScriptPath = new URL('web/assets/js/lab-manager-host-view.js', repoRoot);
const hostActionBindingsScriptPath = new URL('web/assets/js/lab-manager-host-action-bindings.js', repoRoot);
const hostFeatureScriptPath = new URL('web/assets/js/lab-manager-host-feature.js', repoRoot);
const opsAccessScriptPath = new URL('web/assets/js/lab-manager-ops-access.js', repoRoot);
const operationsLifecycleScriptPath = new URL('web/assets/js/lab-manager-operations-lifecycle.js', repoRoot);
const modalBindingsScriptPath = new URL('web/assets/js/lab-manager-modal-bindings.js', repoRoot);
const hostActionsScriptPath = new URL('web/assets/js/lab-manager-host-actions.js', repoRoot);
const toastScriptPath = new URL('web/assets/js/core/toast.js', repoRoot);
const notificationsAccessScriptPath = new URL('web/assets/js/lab-manager-notifications-access.js', repoRoot);
const paginationScriptPath = new URL('web/assets/js/core/pagination.js', repoRoot);
const formattersScriptPath = new URL('web/assets/js/core/formatters.js', repoRoot);
const reservationValuesScriptPath = new URL('web/assets/js/lab-manager-reservation-values.js', repoRoot);
const reservationRenderersScriptPath = new URL('web/assets/js/lab-manager-reservation-renderers.js', repoRoot);
const actionableReservationsScriptPath = new URL('web/assets/js/lab-manager-actionable-reservations.js', repoRoot);
const timelineScriptPath = new URL('web/assets/js/lab-manager-timeline.js', repoRoot);
const notificationsConfigScriptPath = new URL('web/assets/js/lab-manager-notifications-config.js', repoRoot);
const notificationsScriptPath = new URL('web/assets/js/lab-manager-notifications.js', repoRoot);
const notificationsFeatureScriptPath = new URL('web/assets/js/lab-manager-notifications-feature.js', repoRoot);
const fmuSyncScriptPath = new URL('web/assets/js/lab-manager-fmu-sync.js', repoRoot);
const aasLinkScriptPath = new URL('web/assets/js/lab-manager-aas-link.js', repoRoot);
const digitalTwinsScriptPath = new URL('web/assets/js/lab-manager-digital-twins.js', repoRoot);
const powerCredentialsScriptPath = new URL('web/assets/js/lab-manager-power-credentials.js', repoRoot);
const powerRenderersScriptPath = new URL('web/assets/js/lab-manager-power-renderers.js', repoRoot);
const powerValuesScriptPath = new URL('web/assets/js/lab-manager-power-values.js', repoRoot);
const powerOperationsScriptPath = new URL('web/assets/js/lab-manager-power-operations.js', repoRoot);
const powerStatusScriptPath = new URL('web/assets/js/lab-manager-power-status.js', repoRoot);
const powerControllersScriptPath = new URL('web/assets/js/lab-manager-power-controllers.js', repoRoot);
const powerPoliciesScriptPath = new URL('web/assets/js/lab-manager-power-policies.js', repoRoot);
const energyFeatureScriptPath = new URL('web/assets/js/lab-manager-energy-feature.js', repoRoot);
const reservationsFeatureScriptPath = new URL('web/assets/js/lab-manager-reservations-feature.js', repoRoot);
const indexPath = new URL('web/lab-manager/index.html', repoRoot);

function createElement(id) {
  const listeners = new Map();
  const classes = new Set();
  const element = {
    id,
    dataset: {},
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    textContent: '',
    innerHTML: '',
    rawInnerHTML: '',
    style: {},
    children: [],
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
    append: (...children) => {
      element.children.push(...children);
    },
    replaceChildren: (...children) => {
      element.children = children;
      element.options = children;
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
  hostInventoryResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ hosts: [], guacamoleUnmatched: [] }),
  }),
  discoverResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({}),
  }),
  provisionResponse = null,
  editHostResponse = null,
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
  powerControllerStatusResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ controllers: [] }),
  }),
  powerCredentialsResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ credentials: [] }),
  }),
  winrmTrustResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ trust: { status: 'missing' } }),
  }),
  winrmTrustPreviewResponse = Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ preview: { status: 'ready', valid: true } }),
  }),
  eventSource = null,
  confirm = () => true,
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
    'provisionHeartbeatPath',
    'editHostModal', 'closeEditHostModal', 'cancelEditHost', 'saveEditHost',
    'editHostOriginalName', 'editHostName', 'editHostAddress', 'editHostMac',
    'editHeartbeatPath',
    'btnTestLoad', 'saveConfigBtn', 'btnTestEmail', 'refreshHostsBtn', 'hostList',
    'guacamoleCandidateList', 'fmuSyncBtn', 'fmuSyncKey', 'fmuSyncLabSelect',
    'fmuSyncFile', 'fmuSyncFileName', 'fmuSyncResult', 'fmuSyncDescription', 'fmuSyncLicense',
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
    'powerControllerTimeoutSeconds',
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
    'winrmTrustModal', 'closeWinrmTrustModal', 'cancelWinrmTrust', 'previewWinrmTrust',
    'saveWinrmTrust', 'verifyWinrmTrust', 'deleteWinrmTrust', 'winrmTrustModalHost',
    'winrmTrustCurrent', 'winrmTrustCertificate', 'winrmTrustCertificateName',
    'winrmTrustPreview', 'winrmTrustPreviewDetails', 'winrmTrustFingerprintConfirmed',
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
    createElement: (tagName) => {
      const element = createElement(tagName);
      if (tagName === 'div') {
        let text = '';
        let html = null;
        Object.defineProperty(element, 'textContent', {
          get: () => text,
          set: (value) => {
            text = String(value ?? '');
            html = null;
          },
        });
        Object.defineProperty(element, 'innerHTML', {
          get: () => html ?? text
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;'),
          set: (value) => {
            html = String(value ?? '');
            element.rawInnerHTML = html;
          },
        });
      }
      return element;
    },
  };
  const promptCalls = [];
  const window = {
    location: {
      origin: 'https://sarlab.dia.uned.es',
      href: 'https://sarlab.dia.uned.es/lab-manager/',
    },
    confirm,
    AuthTokenHandler: {
      showTokenModal: (...args) => promptCalls.push(args),
      getTokenConfigForPath: () => ({ key: 'billing', login: '/admin/login' }),
    },
    ...(eventSource ? { EventSource: eventSource } : {}),
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
    FormData: class FormData {
      append() {}
    },
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
      if (parsedUrl.pathname === '/ops/api/hosts') {
        return Promise.resolve(hostInventoryResponse);
      }
      if (parsedUrl.pathname === '/ops/api/hosts/discover') {
        return Promise.resolve(discoverResponse);
      }
      if (parsedUrl.pathname.startsWith('/ops/api/hosts/') && options.method === 'PATCH' && editHostResponse) {
        const response = typeof editHostResponse === 'function'
          ? editHostResponse(parsedUrl, fetchCalls.length)
          : editHostResponse;
        return Promise.resolve(response);
      }
      if (parsedUrl.pathname === '/ops/api/hosts/provision' && provisionResponse) {
        return Promise.resolve(provisionResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/policies' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerPoliciesResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/controllers' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerControllersResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/controllers/status' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerControllerStatusResponse);
      }
      if (parsedUrl.pathname === '/ops/api/power/credentials' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(powerCredentialsResponse);
      }
      if (parsedUrl.pathname.endsWith('/winrm-trust/preview') && options.method === 'POST') {
        return Promise.resolve(winrmTrustPreviewResponse);
      }
      if (parsedUrl.pathname.endsWith('/winrm-trust') && (!options.method || options.method === 'GET')) {
        return Promise.resolve(winrmTrustResponse);
      }
      return parsedUrl.pathname === '/billing/admin/notifications'
        ? billingResponse
        : Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    },
  });

  vm.runInContext(fs.readFileSync(stateScriptPath, 'utf8'), context, {
    filename: 'state.js',
  });
  vm.runInContext(fs.readFileSync(apiClientScriptPath, 'utf8'), context, {
    filename: 'api-client.js',
  });
  vm.runInContext(fs.readFileSync(activityScriptPath, 'utf8'), context, {
    filename: 'lab-manager-activity.js',
  });
  vm.runInContext(fs.readFileSync(accessPolicyScriptPath, 'utf8'), context, {
    filename: 'lab-manager-access-policy.js',
  });
  vm.runInContext(fs.readFileSync(heartbeatErrorsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-heartbeat-errors.js',
  });
  vm.runInContext(fs.readFileSync(hostsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-hosts.js',
  });
  vm.runInContext(fs.readFileSync(hostRenderersScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-renderers.js',
  });
  vm.runInContext(fs.readFileSync(hostDiscoveryScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-discovery.js',
  });
  vm.runInContext(fs.readFileSync(winrmCredentialsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-credentials.js',
  });
  vm.runInContext(fs.readFileSync(winrmTrustScriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-trust.js',
  });
  vm.runInContext(fs.readFileSync(winrmTrustModalScriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-trust-modal.js',
  });
  vm.runInContext(fs.readFileSync(hostProvisioningScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-provisioning.js',
  });
  vm.runInContext(fs.readFileSync(hostModalsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-modals.js',
  });
  vm.runInContext(fs.readFileSync(hostViewScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-view.js',
  });
  vm.runInContext(fs.readFileSync(hostActionBindingsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-action-bindings.js',
  });
  vm.runInContext(fs.readFileSync(opsAccessScriptPath, 'utf8'), context, {
    filename: 'lab-manager-ops-access.js',
  });
  vm.runInContext(fs.readFileSync(operationsLifecycleScriptPath, 'utf8'), context, {
    filename: 'lab-manager-operations-lifecycle.js',
  });
  vm.runInContext(fs.readFileSync(modalBindingsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-modal-bindings.js',
  });
  vm.runInContext(fs.readFileSync(hostActionsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-actions.js',
  });
  vm.runInContext(fs.readFileSync(hostFeatureScriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-feature.js',
  });
  vm.runInContext(fs.readFileSync(toastScriptPath, 'utf8'), context, {
    filename: 'toast.js',
  });
  vm.runInContext(fs.readFileSync(notificationsAccessScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-access.js',
  });
  vm.runInContext(fs.readFileSync(paginationScriptPath, 'utf8'), context, {
    filename: 'pagination.js',
  });
  vm.runInContext(fs.readFileSync(formattersScriptPath, 'utf8'), context, {
    filename: 'formatters.js',
  });
  vm.runInContext(fs.readFileSync(reservationValuesScriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservation-values.js',
  });
  vm.runInContext(fs.readFileSync(reservationRenderersScriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservation-renderers.js',
  });
  vm.runInContext(fs.readFileSync(actionableReservationsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-actionable-reservations.js',
  });
  vm.runInContext(fs.readFileSync(timelineScriptPath, 'utf8'), context, {
    filename: 'lab-manager-timeline.js',
  });
  vm.runInContext(fs.readFileSync(notificationsConfigScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-config.js',
  });
  vm.runInContext(fs.readFileSync(notificationsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications.js',
  });
  vm.runInContext(fs.readFileSync(notificationsFeatureScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-feature.js',
  });
  vm.runInContext(fs.readFileSync(fmuSyncScriptPath, 'utf8'), context, {
    filename: 'lab-manager-fmu-sync.js',
  });
  vm.runInContext(fs.readFileSync(aasLinkScriptPath, 'utf8'), context, {
    filename: 'lab-manager-aas-link.js',
  });
  vm.runInContext(fs.readFileSync(digitalTwinsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-digital-twins.js',
  });
  vm.runInContext(fs.readFileSync(powerCredentialsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-credentials.js',
  });
  vm.runInContext(fs.readFileSync(powerRenderersScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-renderers.js',
  });
  vm.runInContext(fs.readFileSync(powerValuesScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-values.js',
  });
  vm.runInContext(fs.readFileSync(powerOperationsScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-operations.js',
  });
  vm.runInContext(fs.readFileSync(powerStatusScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-status.js',
  });
  vm.runInContext(fs.readFileSync(powerControllersScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-controllers.js',
  });
  vm.runInContext(fs.readFileSync(powerPoliciesScriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-policies.js',
  });
  vm.runInContext(fs.readFileSync(energyFeatureScriptPath, 'utf8'), context, {
    filename: 'lab-manager-energy-feature.js',
  });
  vm.runInContext(fs.readFileSync(reservationsFeatureScriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservations-feature.js',
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
  assert.equal(activityCall.options.skipAuthPrompt, undefined);

  const actionableCall = fetchCalls.find(({ url }) => String(url).startsWith('/lab-admin/reservations/actionable'));
  assert.ok(actionableCall, 'Actionable Reservations should be loaded when Operations is activated');
  assert.equal(actionableCall.options.credentials, 'include');
  assert.equal(actionableCall.options.skipAuthPrompt, true);
});

test('loads the activity controller before the Lab Manager bootstrap', () => {
  const html = fs.readFileSync(indexPath, 'utf8');
  assert.match(
    html,
      /lab-manager-tabs\.js\?v=workflow-tabs-v1[\s\S]*lab-manager-activity\.js\?v=lab-manager-activity-v1[\s\S]*lab-manager-access-policy\.js\?v=lab-manager-access-policy-v1[\s\S]*lab-manager-heartbeat-errors\.js\?v=lab-manager-heartbeat-errors-v1[\s\S]*lab-manager-hosts\.js\?v=lab-manager-hosts-v1[\s\S]*lab-manager-host-discovery\.js\?v=lab-manager-host-discovery-v1[\s\S]*lab-manager-winrm-credentials\.js\?v=lab-manager-winrm-credentials-v1[\s\S]*lab-manager-winrm-trust\.js\?v=lab-manager-winrm-trust-v1[\s\S]*lab-manager-host-provisioning\.js\?v=lab-manager-host-provisioning-v1[\s\S]*lab-manager-host-actions\.js\?v=lab-manager-host-actions-v1[\s\S]*lab-manager-host-feature\.js\?v=lab-manager-host-feature-v1[\s\S]*core\/toast\.js\?v=lab-manager-toast-v1[\s\S]*lab-manager-notifications-access\.js\?v=lab-manager-notifications-access-v1[\s\S]*core\/pagination\.js\?v=lab-manager-pagination-v1[\s\S]*core\/formatters\.js\?v=lab-manager-formatters-v1[\s\S]*lab-manager-reservation-values\.js\?v=lab-manager-reservation-values-v1[\s\S]*lab-manager-reservation-renderers\.js\?v=lab-manager-reservation-renderers-v1[\s\S]*lab-manager-notifications-config\.js\?v=lab-manager-notifications-config-v1[\s\S]*lab-manager-notifications\.js\?v=lab-manager-notifications-v1[\s\S]*lab-manager-notifications-feature\.js\?v=lab-manager-notifications-feature-v1[\s\S]*lab-manager-fmu-sync\.js\?v=lab-manager-fmu-sync-v1[\s\S]*lab-manager-aas-link\.js\?v=lab-manager-aas-link-v1[\s\S]*lab-manager-digital-twins\.js\?v=lab-manager-digital-twins-v1[\s\S]*lab-manager-power-credentials\.js\?v=lab-manager-power-credentials-v1[\s\S]*lab-manager-power-renderers\.js\?v=lab-manager-power-renderers-v12[\s\S]*lab-manager-power-values\.js\?v=lab-manager-power-values-v6[\s\S]*lab-manager-power-operations\.js\?v=lab-manager-power-operations-v1[\s\S]*lab-manager-power-status\.js\?v=lab-manager-power-status-v2[\s\S]*lab-manager-power-controllers\.js\?v=lab-manager-power-controllers-v5[\s\S]*lab-manager-power-policies\.js\?v=lab-manager-power-policies-v4[\s\S]*lab-manager-energy-feature\.js\?v=lab-manager-energy-feature-v2[\s\S]*lab-manager-reservations-feature\.js\?v=lab-manager-reservations-feature-v1[\s\S]*lab-manager\.js\?v=workflow-tabs-v18/,
  );
});

test('places Lab Station Ops before Actionable Reservations', () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  const sectionOrderFor = (title) => {
    const titlePosition = html.indexOf(`<h2>${title}</h2>`);
    assert.ok(titlePosition >= 0);
    const sectionStart = html.lastIndexOf('<section', titlePosition);
    const sectionEnd = html.indexOf('>', sectionStart);
    const order = html.slice(sectionStart, sectionEnd).match(/data-lm-order="(\d+)"/);
    assert.ok(order);
    return Number(order[1]);
  };
  assert.ok(sectionOrderFor('Lab Station Ops') < sectionOrderFor('Actionable Reservations'));
});

test('reserves a tall, explicit scroll area for actionable reservation details', () => {
  const stylesheet = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(
    stylesheet,
    /\.reservation-card \.reservation-list\s*\{[\s\S]*min-height:\s*540px;[\s\S]*height:\s*540px;[\s\S]*overflow-y:\s*auto;/,
  );
  assert.match(
    stylesheet,
    /@media \(min-width: 701px\)[\s\S]*\.reservation-card \.reservation-list\s*\{[\s\S]*min-height:\s*540px;[\s\S]*height:\s*540px;[\s\S]*max-height:\s*540px;/,
  );
});

test('places the cancellation reason selector below the cancellation button', () => {
  const stylesheet = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');
  const script = fs.readFileSync(reservationRenderersScriptPath, 'utf8');

  assert.match(
    stylesheet,
    /\.reservation-item-actions\s*\{[^}]*flex-direction:\s*column;[^}]*align-items:\s*flex-end;/,
  );
  assert.match(
    script,
    /data-action="cancel-reservation"[\s\S]*class="reservation-reason"/,
  );
});

test('keeps power output and policy toggle fields aligned in their grids', () => {
  const stylesheet = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(
    stylesheet,
    /\.power-controller-outlet-fields\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit, minmax\(150px, 1fr\)\);/,
  );
  assert.match(
    stylesheet,
    /\.power-controller-outlet-protected-field\s*\{\s*justify-self:\s*stretch;\s*\}/,
  );
  assert.match(
    stylesheet,
    /\.power-checkbox-field\s*\{\s*align-self:\s*start;\s*\}/,
  );
  assert.match(
    stylesheet,
    /\.power-policy-toolbar\s*\{\s*align-items:\s*start;/,
  );
});

test('styles AAS link removal and uses an English custom FMU file picker', () => {
  const stylesheet = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');
  const markup = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');

  assert.match(stylesheet, /\.danger-btn\s*\{[^}]*background:[^}]*color:[^}]*border/);
  assert.match(stylesheet, /\.file-picker\s*\{[^}]*display:\s*flex/);
  assert.match(stylesheet, /\.file-picker-button\s*\{[^}]*cursor:\s*pointer/);
  assert.match(markup, /<label class="file-picker-button" for="fmuSyncFile">Choose file<\/label>/);
  assert.match(markup, /id="fmuSyncFileName"[^>]*>No file chosen<\/span>/);
});

test('updates the English FMU file picker name after choosing a file', () => {
  const { elements } = loadLabManager({});
  const fileInput = elements.get('fmuSyncFile');
  const fileName = elements.get('fmuSyncFileName');

  fileInput.files = [{ name: 'spring-damper.aasx' }];
  fileInput.dispatchEvent({ type: 'change' });

  assert.equal(fileName.textContent, 'spring-damper.aasx');
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

test('confirms reason 8 as a provider service-failure report for a confirmed reservation', async () => {
  const confirmationMessages = [];
  const { elements, fetchCalls } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
    confirm: (message) => {
      confirmationMessages.push(message);
      return true;
    },
  });
  const reservationList = elements.get('upcomingReservationsList');
  const row = {
    dataset: {
      reservationKey: `0x${'ba'.repeat(32)}`,
      reservationStatus: '1',
    },
    querySelector: (selector) => selector === '[data-reservation-reason]'
      ? { value: '8', disabled: false }
      : null,
  };
  const button = {
    disabled: false,
    closest: (selector) => {
      if (selector === '[data-action="cancel-reservation"]') return button;
      if (selector === '.reservation-item') return row;
      return null;
    },
  };

  reservationList.dispatchEvent({ type: 'click', target: button });
  await new Promise((resolve) => setImmediate(resolve));

  assert.match(confirmationMessages[0], /Report provider service failure/);
  const cancellation = fetchCalls.find(({ options }) => options.method === 'POST');
  assert.deepEqual(JSON.parse(cancellation.options.body), { reasonCode: 8 });
  assert.equal(elements.get('toast').textContent, 'Provider service-failure report submitted');
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

test('renders the provider service-failure action for an expired confirmed reservation in the attestation grace period', async () => {
  const now = Math.floor(Date.now() / 1000);
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
        reservations: [{
          reservationKey: `0x${'ef'.repeat(32)}`,
          status: 1,
          statusLabel: 'CONFIRMED',
          cancellable: true,
          start: now - 3600,
          end: now - 1800,
          cancellationOptions: [{
            reasonCode: 8,
            label: 'Service failure',
            deadline: now + 3600,
            reputationPenalty: -3,
          }],
        }],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));

  const rendered = elements.get('upcomingReservationsList').innerHTML;
  assert.match(rendered, /CONFIRMED · ACCESS WINDOW ENDED/);
  assert.match(rendered, /Report service failure/);
  assert.doesNotMatch(rendered, />\s*Cancel reservation\s*</);
});

test('updates the cancellation action label when reason 8 is selected', () => {
  const { elements } = loadLabManager({});
  const reservationList = elements.get('upcomingReservationsList');
  const button = { textContent: 'Cancel reservation' };
  const row = {
    dataset: { reservationStatus: '1' },
    querySelector: (selector) => selector === '[data-action="cancel-reservation"]'
      ? button
      : null,
  };
  const reason = {
    value: '8',
    closest: (selector) => selector === '[data-reservation-reason]' || selector === '.reservation-item'
      ? selector === '.reservation-item' ? row : reason
      : null,
  };

  reservationList.dispatchEvent({ type: 'change', target: reason });

  assert.equal(button.textContent, 'Report service failure');
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
          outlets: [{ outlet: '1', logicalName: 'Bench outlet' }],
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
      controllerId: 'pdu-1',
      outlet: '1',
      action: 'on',
      required: true,
      readBackRequired: true,
      delayBeforeSeconds: 0,
      delayAfterSeconds: 0,
      timeoutSeconds: 20,
      retryCount: 0,
      allowProtected: false,
      conditions: {},
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
      timeoutSeconds: 3,
      retries: 1,
    },
    outlets: [{
      outlet: '1',
      logicalName: '',
      protected: false,
      defaultState: 'off',
    }],
  });
});

test('suggests a stable controller ID from the selected driver and host', async () => {
  const { elements } = loadLabManager({
    billingResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerControllerDriver').value = 'apc-powernet-snmp';
  elements.get('powerControllerDriver').dispatchEvent({ type: 'change' });
  elements.get('powerControllerHost').value = '10.192.38.80';
  elements.get('powerControllerHost').dispatchEvent({ type: 'input' });

  assert.equal(elements.get('powerControllerId').value, 'apc-10-192-38-80');

  elements.get('powerControllerId').value = 'lab-pdu-main';
  elements.get('powerControllerId').dispatchEvent({ type: 'input' });
  elements.get('powerControllerHost').value = '10.192.38.81';
  elements.get('powerControllerHost').dispatchEvent({ type: 'input' });
  assert.equal(elements.get('powerControllerId').value, 'lab-pdu-main');
});

test('offers compatible stored credentials in the controller reference selector', async () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  assert.match(html, /<select id="powerControllerCredentialRef">/);
  assert.doesNotMatch(html, /<input[^>]+id="powerControllerCredentialRef"/);

  const { elements } = loadLabManager({
    powerCredentialsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ credentials: [
        { credentialRef: 'apc-ap7920-snmp', type: 'snmpv3' },
        { credentialRef: 'netio-lab-01-http', type: 'netio-http-basic' },
      ] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('powerControllerDriver').value = 'apc-powernet-snmp';
  elements.get('powerControllerDriver').dispatchEvent({ type: 'change' });
  const credentialSelect = elements.get('powerControllerCredentialRef');
  assert.match(credentialSelect.innerHTML, /apc-ap7920-snmp/);
  assert.doesNotMatch(credentialSelect.innerHTML, /netio-lab-01-http/);

  elements.get('powerControllerDriver').value = 'netio-json';
  elements.get('powerControllerDriver').dispatchEvent({ type: 'change' });
  assert.match(credentialSelect.innerHTML, /netio-lab-01-http/);
  assert.doesNotMatch(credentialSelect.innerHTML, /apc-ap7920-snmp/);
});

test('shows only controller names in the existing controller selector', async () => {
  const { elements } = loadLabManager({
    powerControllersResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ controllers: [{
        id: 'apc-10-192-38-80',
        name: 'APC AP7920',
        driver: 'apc-powernet-snmp',
        enabled: true,
        host: '10.192.38.80',
        port: 161,
        credentialRef: 'apc-ap7920-snmp',
        config: { profile: 'legacy', timeoutSeconds: 2, retries: 1 },
        outlets: [{ outlet: '1' }],
      }] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  const controllerOption = elements.get('powerControllerSelect').options.find(option =>
    option.value === 'apc-10-192-38-80');
  assert.ok(controllerOption);
  assert.equal(controllerOption.textContent, 'APC AP7920');
});

test('renders the controller catalog before loading live power status', async () => {
  let resolveStatus;
  const statusResponse = new Promise((resolve) => {
    resolveStatus = resolve;
  });
  const { elements, fetchCalls } = loadLabManager({
    powerControllersResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ controllers: [{
        id: 'pdu-lab-01',
        name: 'Bench PDU',
        driver: 'apc-powernet-snmp',
          outlets: [{ outlet: '1', logicalName: 'Bench outlet' }],
      }] }),
    }),
    powerControllerStatusResponse: statusResponse,
  });

  await new Promise((resolve) => setImmediate(resolve));

  const controllerOption = elements.get('powerControllerSelect').options.find(option =>
    option.value === 'pdu-lab-01');
  assert.ok(controllerOption, 'catalog should populate the existing controller selector');
  assert.match(elements.get('powerControllerList').options.at(-1).rawInnerHTML, /checking/);
  assert.equal(
    fetchCalls.some(({ url }) => url === '/ops/api/power/controllers/status'),
    true,
  );

  resolveStatus({
    ok: true,
    status: 200,
    json: async () => ({ controllers: [{
      id: 'pdu-lab-01',
      discovery: { reachable: true },
      outlets: [{ outlet: '1', state: 'off' }],
    }] }),
  });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  assert.match(elements.get('powerControllerList').options.at(-1).rawInnerHTML, /reachable/);
  assert.match(elements.get('powerControllerList').options.at(-1).rawInnerHTML, />off</);
});

test('forces a live status refresh from the power controller refresh button', async () => {
  const { elements, fetchCalls } = loadLabManager({
    powerControllersResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ controllers: [{
        id: 'pdu-lab-01',
        name: 'Bench PDU',
        driver: 'mock',
        outlets: [{ outlet: '1' }],
      }] }),
    }),
    powerControllerStatusResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ controllers: [{
        id: 'pdu-lab-01',
        discovery: { reachable: true },
        outlets: [{ outlet: '1', state: 'off' }],
      }] }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  elements.get('refreshPowerControllersBtn').click();
  await new Promise((resolve) => setImmediate(resolve));

  const statusCalls = fetchCalls.filter(({ url }) => String(url).startsWith('/ops/api/power/controllers/status'));
  assert.ok(statusCalls.length >= 2);
  assert.match(statusCalls.at(-1).url, /[?&]refresh=true/);
});

test('orders controller fields so host and driver precede the generated ID', () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  const formStart = html.indexOf('id="powerControllerSelect"');
  const formEnd = html.indexOf('id="powerControllerNetioPathField"');
  const form = html.slice(formStart, formEnd);
  const orderedFields = [
    'powerControllerSelect',
    'powerControllerName',
    'powerControllerDriver',
    'powerControllerHost',
    'powerControllerEnabled',
    'powerControllerId',
    'powerControllerPort',
    'powerControllerCredentialRef',
  ];
  const positions = orderedFields.map(id => form.indexOf(`id="${id}"`));
  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right));
});

test('removes the redundant controller SNMP version and default editor prompt', () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  const script = fs.readFileSync(new URL('web/assets/js/lab-manager.js', repoRoot), 'utf8');
  assert.doesNotMatch(html, /powerControllerSnmpVersion/);
  assert.doesNotMatch(script, /powerControllerSnmpVersion/);
  assert.doesNotMatch(html, /Select an existing controller or configure a new one\./);
  assert.doesNotMatch(script, /Select an existing controller or configure a new one\./);
});

test('removes the default power policy editor prompt', () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  const script = fs.readFileSync(new URL('web/assets/js/lab-manager.js', repoRoot), 'utf8');
  assert.doesNotMatch(html, /Select an existing policy or a laboratory defined above\./);
  assert.doesNotMatch(script, /Select a laboratory and configure the policy fields\./);
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

test('prefers managed lab names in operations reservations and lab selectors', async () => {
  const { elements } = loadLabManager({
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
          { labId: '1', name: 'State Space', resourceType: 1, accessKey: 'StateSpace.fmu', listed: true },
          { labId: '2', name: 'Furuta Inverted Pendulum', resourceType: 0, accessKey: 'guac:id:2', listed: true },
        ],
      }),
    }),
    actionableResponse: {
      ok: true,
      status: 200,
      json: async () => ({
          reservations: [{
            reservationKey: '0xreservation',
            labId: '1',
            status: 2,
            statusLabel: 'ACCESS_AUTHORIZED',
            start: 1_800_000_000,
            end: 1_800_003_600,
            priceCredits: '0.8',
            providerShareCredits: '0.7',
            renter: '0xrenter',
            institutionAddress: '0xinstitution',
            cancellable: false,
            cancellationOptions: [],
          }],
          pagination: { returned: 1, hasMore: false, total: 1 },
        }),
    },
  });

  await new Promise((resolve) => setImmediate(resolve));

  assert.match(
    elements.get('powerPolicyLabSelect').options.map((option) => option.textContent).join('\n'),
    /State Space/,
  );
  assert.match(
    elements.get('fmuSyncKey').options.map((option) => option.textContent).join('\n'),
    /State Space/,
  );
  assert.match(elements.get('upcomingReservationsList').innerHTML, /State Space/);
  assert.doesNotMatch(elements.get('upcomingReservationsList').innerHTML, /Lab #1/);
});

test('groups connections by station and automatically links its local physical labs', async () => {
  const connection = {
    id: 42,
    name: 'Siemens Admin',
    protocol: 'rdp',
    hostname: '10.192.38.82',
    port: '3389',
  };
  const secondConnection = {
    id: 43,
    name: 'Siemens LABUSER',
    protocol: 'rdp',
    hostname: '10.192.38.82',
    port: '3389',
  };
  const { elements, fetchCalls } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [],
        guacamoleAvailable: true,
        guacamoleUnmatched: [connection, secondConnection],
      }),
    }),
    discoverResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'winrm-reachable',
        connection,
        checks: { winrm: { '5986': true } },
        opsHostDraft: { address: connection.hostname },
      }),
    }),
    labsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        labs: [{
          labId: '7',
          name: 'Siemens Admin',
          resourceType: 0,
          accessURI: 'https://sarlab.dia.uned.es/guacamole',
          accessKey: 'guac:id:42',
          listed: true,
        }, {
          labId: '10',
          name: 'Siemens LABUSER',
          resourceType: 0,
          accessURI: 'https://sarlab.dia.uned.es/guacamole',
          accessKey: 'guac:id:43',
          listed: true,
        }, {
          labId: '8',
          name: 'Siemens Admin on Lite A',
          resourceType: 0,
          accessURI: 'https://lite-a.example.edu/guacamole',
          accessKey: 'guac:id:42',
          listed: true,
        }, {
          labId: '9',
          name: 'Another local lab',
          resourceType: 0,
          accessURI: 'https://sarlab.dia.uned.es/guacamole',
          accessKey: 'guac:id:7',
          listed: true,
        }],
      }),
    }),
  });

  const flush = () => new Promise((resolve) => setImmediate(resolve));
  await flush();
  const candidateList = elements.get('guacamoleCandidateList');
  assert.equal(candidateList.options.length, 1, 'Connections targeting one station should render as one candidate');
  assert.match(elements.get('opsHint').textContent, /1 Lab Station candidate awaiting configuration\./);
  const initialRow = candidateList.options.at(-1);
  const checkButton = {
    dataset: { action: 'probe-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? checkButton : initialRow,
  };
  candidateList.dispatchEvent({ type: 'click', target: checkButton });
  await flush();
  await flush();

  const configuredRow = candidateList.options.at(-1);
  const configureButton = {
    dataset: { action: 'configure-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? configureButton : configuredRow,
  };
  candidateList.dispatchEvent({ type: 'click', target: configureButton });
  await flush();

  assert.equal(elements.get('provisionHostModal').classList.contains('show'), true);
  assert.equal(elements.get('provisionHostLabs'), undefined, 'Lab selection should not be exposed in the station modal');

  elements.get('saveProvisionHost').click();
  await flush();

  const provisionCall = fetchCalls.find(({ url }) => String(url) === '/ops/api/hosts/provision');
  assert.ok(provisionCall, 'Saving a station should call the provisioning endpoint');
  const provisionPayload = JSON.parse(provisionCall.options.body);
  assert.deepEqual(provisionPayload.labs, ['7', '10']);
  assert.deepEqual(provisionPayload.validLabIds, ['7', '10']);
});

test('does not require an administrative connection to have a published lab', async () => {
  const connection = {
    id: 44,
    name: 'Siemens Administration',
    protocol: 'rdp',
    hostname: '10.192.38.90',
    port: '3389',
  };
  const { elements, fetchCalls } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [],
        guacamoleAvailable: true,
        guacamoleUnmatched: [connection],
      }),
    }),
    discoverResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'winrm-reachable',
        connection,
        checks: { winrm: { '5986': true } },
        opsHostDraft: { address: connection.hostname },
      }),
    }),
    labsResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ labs: [] }),
    }),
  });

  const flush = () => new Promise((resolve) => setImmediate(resolve));
  await flush();
  const candidateList = elements.get('guacamoleCandidateList');
  const row = candidateList.options.at(-1);
  const checkButton = {
    dataset: { action: 'probe-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? checkButton : row,
  };
  candidateList.dispatchEvent({ type: 'click', target: checkButton });
  await flush();
  await flush();

  const configuredRow = candidateList.options.at(-1);
  const configureButton = {
    dataset: { action: 'configure-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? configureButton : configuredRow,
  };
  candidateList.dispatchEvent({ type: 'click', target: configureButton });
  await flush();
  elements.get('saveProvisionHost').click();
  await flush();

  const provisionCall = fetchCalls.find(({ url }) => String(url) === '/ops/api/hosts/provision');
  const provisionPayload = JSON.parse(provisionCall.options.body);
  assert.deepEqual(provisionPayload.labs, []);
  assert.equal('validLabIds' in provisionPayload, false);
});

test('shows the provisioning request id when the backend reports an internal failure', async () => {
  const connection = {
    id: 45,
    name: 'Station With Backend Failure',
    protocol: 'rdp',
    hostname: '10.192.38.91',
    port: '3389',
  };
  const { elements } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [],
        guacamoleAvailable: true,
        guacamoleUnmatched: [connection],
      }),
    }),
    discoverResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'winrm-reachable',
        connection,
        checks: { winrm: { '5986': true } },
        opsHostDraft: { address: connection.hostname },
      }),
    }),
    provisionResponse: Promise.resolve({
      ok: false,
      status: 500,
      json: async () => ({
        error: 'Internal server error',
        code: 'INTERNAL_ERROR',
        requestId: 'ops-request-45',
      }),
    }),
  });

  const flush = () => new Promise((resolve) => setImmediate(resolve));
  await flush();
  const candidateList = elements.get('guacamoleCandidateList');
  const row = candidateList.options.at(-1);
  const checkButton = {
    dataset: { action: 'probe-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? checkButton : row,
  };
  candidateList.dispatchEvent({ type: 'click', target: checkButton });
  await flush();
  await flush();

  const configuredRow = candidateList.options.at(-1);
  const configureButton = {
    dataset: { action: 'configure-candidate' },
    closest: (selector) => selector === 'button[data-action]' ? configureButton : configuredRow,
  };
  candidateList.dispatchEvent({ type: 'click', target: configureButton });
  await flush();
  elements.get('saveProvisionHost').click();
  await flush();

  assert.equal(
    elements.get('toast').textContent,
    'Configure host failed: Internal server error (request ID ops-request-45)',
  );
});

test('edits a dynamic ops host from the pencil action', async () => {
  const { elements, fetchCalls } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{
          name: '10.192.38.82',
          address: '10.192.38.82',
          mac: '00:11:22:33:44:55',
          heartbeatPath: 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json',
          editable: true,
          winrmConfigured: false,
          guacamole: { status: 'none', connections: [] },
        }],
        guacamoleUnmatched: [],
      }),
    }),
    editHostResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ host: { name: 'siemens-admin' } }),
    }),
  });

  const flush = () => new Promise((resolve) => setImmediate(resolve));
  await flush();
  const hostList = elements.get('hostList');
  const row = hostList.options.at(-1);
  const editButton = {
    dataset: { action: 'edit-host' },
    closest: (selector) => selector === 'button[data-action]' ? editButton : row,
  };
  hostList.dispatchEvent({ type: 'click', target: editButton });

  assert.equal(elements.get('editHostModal').classList.contains('show'), true);
  assert.equal(elements.get('editHostName').value, '10.192.38.82');
  assert.equal(elements.get('editHostAddress').value, '10.192.38.82');
  assert.equal(elements.get('editHostMac').value, '00:11:22:33:44:55');
  assert.equal(
    elements.get('editHeartbeatPath').value,
    'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json',
  );

  elements.get('editHostName').value = 'siemens-admin';
  elements.get('editHostMac').value = '00-22-33-44-55-66';
  elements.get('editHeartbeatPath').value = 'C:\\Lab Station\\labstation\\data\\telemetry\\heartbeat.json';
  elements.get('saveEditHost').click();
  await flush();
  await flush();

  const editCall = fetchCalls.find(({ url, options }) =>
    options.method === 'PATCH' && url === '/ops/api/hosts/10.192.38.82');
  assert.ok(editCall, 'Editing a host should call the host update endpoint');
  assert.deepEqual(JSON.parse(editCall.options.body), {
    name: 'siemens-admin',
    mac: '00-22-33-44-55-66',
    heartbeatPath: 'C:\\Lab Station\\labstation\\data\\telemetry\\heartbeat.json',
  });
  assert.equal(elements.get('editHostModal').classList.contains('show'), false);
});

test('uses a self-contained visible pencil icon for editable ops hosts', () => {
  const script = fs.readFileSync(hostRenderersScriptPath, 'utf8');
  const styles = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(
    script,
    /host-edit-btn[\s\S]*host-edit-icon[\s\S]*<path d="M3 17\.25V21h3\.75L17\.81 9\.94l-3\.75-3\.75L3 17\.25z/,
  );
  assert.match(styles, /\.host-edit-icon[\s\S]*width: 16px[\s\S]*height: 16px[\s\S]*fill: currentColor/);
});

test('renders station identity, connection counts, operation history and WinRM trust states', () => {
  const script = fs.readFileSync(hostRenderersScriptPath, 'utf8');
  const hostView = fs.readFileSync(hostViewScriptPath, 'utf8');
  const styles = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(script, /host-status-text/);
  assert.match(script, /Address: <span class="mono">\$\{safeAddress\}/);
  assert.match(script, /Last heartbeat: \$\{safeUpdated\}/);
  assert.match(script, /Last activity:/);
  assert.match(script, /WinRM TLS trust:/);
  assert.match(script, /formatConnectionsStatus/);
  assert.match(script, /return 'No connections'/);
  assert.match(script, /\$\{connections\.length\} connections/);
  assert.match(script, /meta\.winrmTrustStatus/);
  assert.match(script, /formatBool\(localSession\)/);
  assert.match(script, /formatBool\(localMode\)/);
  assert.match(script, /host-state-column/);
  assert.match(script, /host-status-action/);
  assert.doesNotMatch(script, /<button class="mini-btn" data-action="set-winrm-credentials">WinRM Credentials<\/button>/);
  assert.doesNotMatch(script, /Guacamole: \$\{guacamoleStatusMarkup\}/);
  assert.doesNotMatch(script, /ambiguous - \$\{connections\.length\} matches/);
  assert.match(script, /guacamole-match-trigger/);
  assert.match(script, /guacamole-match-popover/);
  assert.match(script, /Connections for this station/);
  assert.match(script, /connection\?\.name/);
  assert.match(styles, /\.host-status-text\.warn[\s\S]*color: var\(--warning\)/);
  assert.match(styles, /\.host-status-action[\s\S]*display: inline/);
  assert.match(styles, /\.host-state-column[\s\S]*display: flex/);
  assert.match(styles, /\.host-history[\s\S]*display: flex/);
  assert.match(hostView, /setupGuacamoleMatchPopover/);
  assert.match(hostView, /addEventListener\('mouseenter'/);
  assert.match(hostView, /addEventListener\('focusin'/);
  assert.match(styles, /\.guacamole-match-popover[\s\S]*position: fixed/);
  assert.match(styles, /\.guacamole-match-popover\.is-visible[\s\S]*opacity: 1/);
});

test('adds spacing below operations and reservation timeline hints', () => {
  const index = fs.readFileSync(indexPath, 'utf8');
  const styles = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(index, /<div class="hint hint-spaced" id="opsHint">/);
  assert.match(index, /<div class="hint mt-4 hint-spaced">Lab Station candidates awaiting configuration:<\/div>/);
  assert.match(index, /<div class="hint hint-spaced">Paste the on-chain reservation key/);
  assert.match(styles, /\.hint-spaced\s*\{\s*margin-bottom: 0\.75rem;/);
});

test('keeps energy credential metadata separated from its rotate action', () => {
  const script = fs.readFileSync(new URL('web/assets/js/lab-manager.js', repoRoot), 'utf8');
  const credentialsScript = fs.readFileSync(new URL('web/assets/js/lab-manager-power-credentials.js', repoRoot), 'utf8');
  const styles = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.doesNotMatch(script, /<div class="power-controller-row power-credential-row">/);
  assert.match(credentialsScript, /<div class="power-controller-row power-credential-row">/);
  assert.match(styles, /\.power-credential-row\s*\{[\s\S]*display:\s*flex;[\s\S]*gap:\s*12px;/);
});

test('renders the complete station status card with truthful empty and configured states', async () => {
  const { elements } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{
          name: 'PC-Siemens',
          address: '192.168.1.52',
          winrmConfigured: true,
          winrmTrustConfigured: true,
          winrmTrustStatus: 'ready',
          guacamole: {
            status: 'multiple',
            connections: [
              { name: 'Primary RDP', protocol: 'rdp', port: 3389 },
              { name: 'Backup RDP', protocol: 'rdp', port: 3390 },
            ],
          },
        }],
        guacamoleUnmatched: [],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  const row = elements.get('hostList').options.at(-1);
  assert.match(row.rawInnerHTML, /Address: <span class="mono">192\.168\.1\.52<\/span>/);
  assert.match(row.rawInnerHTML, /Last heartbeat: not available/);
  assert.match(row.rawInnerHTML, />2 connections<\/span>/);
  assert.doesNotMatch(row.rawInnerHTML, /ambiguous/);
  assert.match(row.rawInnerHTML, /class="host-state-column"[\s\S]*Last activity:/);
  assert.match(row.rawInnerHTML, /WinRM credentials: <button type="button" class="host-status-action" data-action="set-winrm-credentials"[^>]*>[\s\S]*<span class="host-status-text good">configured<\/span>/);
  assert.doesNotMatch(row.rawInnerHTML, /class="mini-btn" data-action="set-winrm-credentials"/);
  assert.match(row.rawInnerHTML, /WinRM TLS trust: <button type="button" class="host-status-action" data-action="manage-winrm-trust"[^>]*>[\s\S]*<span class="host-status-text good">ready<\/span>/);
  assert.match(row.rawInnerHTML, /Forced logoff: not available/);
  assert.match(row.rawInnerHTML, /Power action: not available/);
  assert.match(row.rawInnerHTML, /Ready: n\/a/);
  assert.match(row.rawInnerHTML, /Local session: n\/a/);
  assert.match(row.rawInnerHTML, /Local mode: n\/a/);
});

test('enables Verify connection only for saved ready trust and configured credentials', async () => {
  const trustStatuses = ['missing', 'invalid', 'expired', 'not-yet-valid'];
  const flush = () => new Promise((resolve) => setImmediate(resolve));

  const { elements: missingCredentialsElements } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{ name: 'PC-Siemens', address: '192.168.1.52', winrmConfigured: false }],
        guacamoleUnmatched: [],
      }),
    }),
    winrmTrustResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ trust: { status: 'ready' } }),
    }),
  });

  await flush();
  const missingCredentialsRow = missingCredentialsElements.get('hostList').options.at(-1);
  const missingCredentialsManageButton = {
    dataset: { action: 'manage-winrm-trust' },
    closest: (selector) => selector === 'button[data-action]' ? missingCredentialsManageButton : missingCredentialsRow,
  };
  missingCredentialsElements.get('hostList').dispatchEvent({
    type: 'click',
    target: missingCredentialsManageButton,
  });
  await flush();
  assert.equal(missingCredentialsElements.get('verifyWinrmTrust').disabled, true, 'credentials are required');

  for (const status of trustStatuses) {
    const { elements } = loadLabManager({
      activeTabs: ['operations'],
      hostInventoryResponse: Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          hosts: [{ name: 'PC-Siemens', address: '192.168.1.52', winrmConfigured: true }],
          guacamoleUnmatched: [],
        }),
      }),
      winrmTrustResponse: Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ trust: { status } }),
      }),
    });

    await flush();
    const row = elements.get('hostList').options.at(-1);
    const manageButton = {
      dataset: { action: 'manage-winrm-trust' },
      closest: (selector) => selector === 'button[data-action]' ? manageButton : row,
    };
    elements.get('hostList').dispatchEvent({ type: 'click', target: manageButton });
    await flush();

    assert.equal(elements.get('verifyWinrmTrust').disabled, true, `status=${status}`);
  }

  const { elements, fetchCalls } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{ name: 'PC-Siemens', address: '192.168.1.52', winrmConfigured: true }],
        guacamoleUnmatched: [],
      }),
    }),
    winrmTrustResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ trust: { status: 'ready' } }),
    }),
  });

  await flush();
  const row = elements.get('hostList').options.at(-1);
  const manageButton = {
    dataset: { action: 'manage-winrm-trust' },
    closest: (selector) => selector === 'button[data-action]' ? manageButton : row,
  };
  elements.get('hostList').dispatchEvent({ type: 'click', target: manageButton });
  await flush();
  assert.match(elements.get('winrmTrustCurrent').children[0]?.textContent || '', /Current trust: ready/);
  assert.equal(elements.get('verifyWinrmTrust').disabled, false);

  elements.get('winrmTrustCertificate').files = [{ name: 'winrm-server.cer' }];
  elements.get('winrmTrustCertificate').dispatchEvent({ type: 'change' });
  elements.get('previewWinrmTrust').click();
  await flush();
  assert.equal(elements.get('verifyWinrmTrust').disabled, false, 'preview must not revoke an existing saved trust');

  const heartbeatCallsBeforeVerify = fetchCalls.filter(({ url }) => String(url) === '/ops/api/heartbeat/poll').length;
  elements.get('verifyWinrmTrust').click();
  await flush();
  assert.equal(
    fetchCalls.filter(({ url }) => String(url) === '/ops/api/heartbeat/poll').length,
    heartbeatCallsBeforeVerify + 1,
  );
});

test('keeps Verify connection disabled while the saved trust state is loading', async () => {
  let resolveTrust;
  const pendingTrustResponse = new Promise((resolve) => {
    resolveTrust = resolve;
  });
  const { elements } = loadLabManager({
    activeTabs: ['operations'],
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{ name: 'PC-Siemens', address: '192.168.1.52', winrmConfigured: true }],
        guacamoleUnmatched: [],
      }),
    }),
    winrmTrustResponse: pendingTrustResponse,
  });

  await new Promise((resolve) => setImmediate(resolve));
  const row = elements.get('hostList').options.at(-1);
  const manageButton = {
    dataset: { action: 'manage-winrm-trust' },
    closest: (selector) => selector === 'button[data-action]' ? manageButton : row,
  };
  elements.get('hostList').dispatchEvent({ type: 'click', target: manageButton });
  assert.equal(elements.get('verifyWinrmTrust').disabled, true);

  resolveTrust({
    ok: true,
    status: 200,
    json: async () => ({ trust: { status: 'ready' } }),
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements.get('verifyWinrmTrust').disabled, false);
});

test('does not open heartbeat streams for hosts without WinRM prerequisites', async () => {
  class FakeEventSource {
    static instances = [];
    static CLOSED = 2;

    constructor(url) {
      this.url = url;
      this.readyState = 1;
      FakeEventSource.instances.push(this);
    }

    addEventListener() {}
    close() { this.readyState = FakeEventSource.CLOSED; }
  }

  loadLabManager({
    activeTabs: ['operations'],
    eventSource: FakeEventSource,
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [
          {
            name: '10.192.38.82',
            address: '10.192.38.82',
            winrmConfigured: false,
            editable: true,
          },
          {
            name: 'PC-Siemens',
            address: '192.168.1.52',
            winrmConfigured: true,
            winrmTrustConfigured: false,
            winrmTrustStatus: 'missing',
          },
        ],
        guacamoleUnmatched: [],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(FakeEventSource.instances.length, 0);
});

test('renders classified heartbeat stream errors without exposing the JSON payload', async () => {
  class FakeEventSource {
    static instances = [];
    static CLOSED = 2;

    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.listeners = new Map();
      FakeEventSource.instances.push(this);
    }

    addEventListener(type, handler) { this.listeners.set(type, handler); }
    emit(type, event) { this.listeners.get(type)?.(event); }
    close() { this.readyState = FakeEventSource.CLOSED; }
  }

  const { elements } = loadLabManager({
    activeTabs: ['operations'],
    eventSource: FakeEventSource,
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{
          name: 'PC-Siemens',
          address: '192.168.1.52',
          winrmConfigured: true,
          winrmTrustConfigured: true,
          winrmTrustStatus: 'ready',
        }],
        guacamoleUnmatched: [],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(FakeEventSource.instances.length, 1);
  FakeEventSource.instances[0].emit('error', {
    data: JSON.stringify({
      error: 'WinRM certificate trust is required',
      code: 'WINRM_TRUST_REQUIRED',
      requestId: 'trust-request-1',
      host: 'PC-Siemens',
    }),
  });

  assert.equal(
    elements.get('toast').textContent,
    'Heartbeat unavailable for PC-Siemens: WinRM certificate trust is required',
  );
  assert.doesNotMatch(elements.get('toast').textContent, /\{"error"/);
});

test('keeps the request ID only as a short reference for generic heartbeat errors', async () => {
  class FakeEventSource {
    static instances = [];
    static CLOSED = 2;

    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.listeners = new Map();
      FakeEventSource.instances.push(this);
    }

    addEventListener(type, handler) { this.listeners.set(type, handler); }
    emit(type, event) { this.listeners.get(type)?.(event); }
    close() { this.readyState = FakeEventSource.CLOSED; }
  }

  const { elements } = loadLabManager({
    activeTabs: ['operations'],
    eventSource: FakeEventSource,
    hostInventoryResponse: Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        hosts: [{
          name: 'PC-Siemens',
          address: '192.168.1.52',
          winrmConfigured: true,
          winrmTrustConfigured: true,
          winrmTrustStatus: 'ready',
        }],
        guacamoleUnmatched: [],
      }),
    }),
  });

  await new Promise((resolve) => setImmediate(resolve));
  FakeEventSource.instances[0].emit('error', {
    data: JSON.stringify({
      error: 'Internal server error',
      code: 'INTERNAL_ERROR',
      requestId: 'f33bb129cf1e475f8bc3db34ce2fe5dc',
      host: 'PC-Siemens',
    }),
  });

  assert.equal(
    elements.get('toast').textContent,
    'Heartbeat unavailable for PC-Siemens: temporary Ops Worker error (request ID f33bb129cf1e475f8bc3db34ce2fe5dc)',
  );
  assert.doesNotMatch(elements.get('toast').textContent, /\{"error"/);
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
