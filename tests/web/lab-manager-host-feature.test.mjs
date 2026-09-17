import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-feature.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  return {
    id,
    addEventListener: (type, handler) => listeners.set(type, handler),
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
  };
}

function loadFeature() {
  const ids = [
    'refreshHostsBtn', 'hostList', 'opsHint', 'guacamoleCandidateList',
    'provisionHostModal', 'closeProvisionHostModal', 'cancelProvisionHost', 'saveProvisionHost',
    'winrmCredentialsModal', 'closeWinrmCredentialsModal', 'cancelWinrmCredentials', 'saveWinrmCredentials',
    'winrmTrustModal', 'closeWinrmTrustModal', 'cancelWinrmTrust', 'previewWinrmTrust',
    'saveWinrmTrust', 'verifyWinrmTrust', 'deleteWinrmTrust', 'winrmTrustModalHost',
    'winrmTrustCurrent', 'winrmTrustCertificate', 'winrmTrustCertificateName', 'winrmTrustPreview',
    'winrmTrustPreviewDetails', 'winrmTrustFingerprintConfirmed', 'editHostModal', 'closeEditHostModal',
    'cancelEditHost', 'saveEditHost', 'winrmCredentialRef', 'winrmCredentialAddress',
    'winrmCredentialUser', 'winrmCredentialPassword', 'provisionConnectionId', 'provisionHostName',
    'provisionHostNameCandidates', 'provisionHostAddress', 'provisionHostMac', 'provisionHeartbeatPath',
    'editHostOriginalName', 'editHostName', 'editHostAddress', 'editHostMac', 'editHeartbeatPath',
  ];
  const elements = new Map(ids.map((id) => [id, createElement(id)]));
  const document = {
    querySelector: (selector) => elements.get(selector.slice(1)) || null,
    createElement: (tagName) => createElement(tagName),
  };
  const calls = [];
  const controllers = {
    hosts: {
      loadInventory: (...args) => calls.push(['hosts.loadInventory', ...args]),
      startHeartbeatStream: (...args) => calls.push(['hosts.startHeartbeatStream', ...args]),
      stopHeartbeatStream: (...args) => calls.push(['hosts.stopHeartbeatStream', ...args]),
      refreshAllHosts: (...args) => calls.push(['hosts.refreshAllHosts', ...args]),
      pollHeartbeat: (...args) => calls.push(['hosts.pollHeartbeat', ...args]),
    },
    hostActions: {
      triggerWol: () => {},
      triggerWinrm: () => {},
      toggleLocalMode: () => {},
      syncAasHost: () => {},
    },
    hostDiscovery: { probe: () => {} },
    winrmCredentials: {},
    winrmTrust: {},
    hostProvisioning: {},
    hostModals: {
      openProvision: () => {},
      closeProvision: () => {},
      saveProvision: () => {},
      openEdit: () => {},
      closeEdit: () => {},
      saveEdit: () => {},
      openCredentials: () => {},
      closeCredentials: () => {},
      saveCredentials: () => {},
    },
    hostView: {
      bind: () => calls.push('view.bind'),
      renderHosts: () => calls.push('view.renderHosts'),
      groupCandidates: candidates => candidates,
      findStationCandidate: () => null,
    },
    trustModal: {
      getState: () => ({ activeHost: '' }),
      renderState: () => {},
      renderPreview: () => {},
      updateVerifyState: () => {},
      updateSaveState: () => {},
      handleCertificateSelected: () => {},
      markUnavailable: () => {},
      open: () => {},
      load: () => {},
      close: () => {},
      preview: () => {},
      save: () => {},
      verify: () => {},
      delete: () => {},
    },
    actionBindings: { bind: () => calls.push('action-bindings.bind') },
    modalBindings: { bind: () => calls.push('modal-bindings.bind') },
  };
  const createModule = (name, controller) => ({
    createController: (options) => {
      calls.push(`${name}.create`);
      if (name === 'host-view') {
        assert.equal(options.hostListEl, elements.get('hostList'));
        assert.deepEqual(options.callbacks.onProbeCandidate('station-1'), undefined);
      }
      return controller;
    },
  });
  const window = {
    LabManagerHosts: createModule('hosts', controllers.hosts),
    LabManagerHostRenderers: createModule('host-renderers', {}),
    LabManagerHostDiscovery: createModule('host-discovery', controllers.hostDiscovery),
    LabManagerWinrmCredentials: createModule('winrm-credentials', controllers.winrmCredentials),
    LabManagerWinrmTrust: createModule('winrm-trust', controllers.winrmTrust),
    LabManagerWinrmTrustModal: createModule('trust-modal', controllers.trustModal),
    LabManagerHostProvisioning: createModule('host-provisioning', controllers.hostProvisioning),
    LabManagerHostModals: createModule('host-modals', controllers.hostModals),
    LabManagerHostView: createModule('host-view', controllers.hostView),
    LabManagerHostActionBindings: createModule('action-bindings', controllers.actionBindings),
    LabManagerHostActions: createModule('host-actions', controllers.hostActions),
    LabManagerModalBindings: createModule('modal-bindings', controllers.modalBindings),
  };
  const context = vm.createContext({ document, window, console, FormData: class FormData {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-feature.js',
  });
  return { context, elements, calls };
}

test('host feature composes host controllers and preserves the final binding boundary', () => {
  const { context, elements, calls } = loadFeature();
  const controller = context.window.LabManagerHostFeature.createController({
    documentImpl: context.document,
    windowImpl: context.window,
    fetchImpl: () => Promise.resolve(),
    formDataCtor: context.FormData,
    formatDate: value => String(value),
    formatBool: value => String(value),
    escapeHtml: value => String(value),
    formatHeartbeatError: () => 'heartbeat-error',
    isHeartbeatConfigurationError: () => false,
    loadActivityFeed: () => {},
    updateOpsHint: () => {},
    showOpsWarning: () => {},
    showToast: () => {},
    confirmImpl: () => true,
  });

  controller.initialize();
  assert.equal(calls.at(-1), 'modal-bindings.bind');
  assert.equal(controller.hostListElement, elements.get('hostList'));
  assert.equal(controller.refreshHostsButton, elements.get('refreshHostsBtn'));
  assert.equal(controller.hasHostList(), true);
  assert.deepEqual(controller.groupCandidates(['candidate']), ['candidate']);

  controller.bind();
  assert.deepEqual(calls.slice(-3), [
    'action-bindings.bind',
    'view.renderHosts',
    'view.bind',
  ]);
  elements.get('refreshHostsBtn').dispatchEvent({ type: 'click' });
  assert.equal(calls.at(-1)[0], 'hosts.refreshAllHosts');
  controller.loadHostInventory({ skipAuthPrompt: true });
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), [
    'hosts.loadInventory',
    { skipAuthPrompt: true },
  ]);
});
