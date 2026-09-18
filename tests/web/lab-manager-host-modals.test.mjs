import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-modals.js', repoRoot);

function loadModule() {
  const context = vm.createContext({
    console,
    URL,
    window: { location: { origin: 'https://gateway.example' }, confirm: () => true },
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-modals.js',
  });
  return context.window.LabManagerHostModals;
}

function element(overrides = {}) {
  return {
    value: '',
    disabled: false,
    innerHTML: '',
    textContent: '',
    classList: { add() {}, remove() {} },
    appendChild(child) { this.child = child; return child; },
    ...overrides,
  };
}

function modalFields() {
  return {
    provisionModal: element(),
    provisionSaveButton: element(),
    provisionConnectionId: element(),
    provisionHostName: element(),
    provisionHostNameCandidates: element({ options: [] }),
    provisionHostAddress: element(),
    provisionHostMac: element(),
    provisionHostBroadcast: element(),
    provisionLabstationExe: element(),
    provisionLocalModeFlagPath: element(),
    provisionHeartbeatPath: element(),
    provisionEventsPath: element(),
    editModal: element(),
    editOriginalName: element(),
    editName: element(),
    editAddress: element(),
    editMac: element(),
    editBroadcast: element(),
    editLabstationExe: element(),
    editLocalModeFlagPath: element(),
    editHeartbeatPath: element(),
    editEventsPath: element(),
    editSaveButton: element(),
    credentialsModal: element(),
    credentialRef: element(),
    credentialAddress: element(),
    credentialUser: element(),
    credentialPassword: element(),
    credentialSaveButton: element(),
  };
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('keeps provision, edit and credential modal payloads inside one host controller', async () => {
  const module = loadModule();
  const fields = modalFields();
  const requests = [];
  const events = [];
  const station = {
    address: '10.0.0.8',
    nameCandidates: ['station-8'],
    connections: [{ id: 'conn-8', hostname: '10.0.0.8', selector: 'guac:conn-8' }],
  };
  const controller = module.createController({
    fields,
    hostMetadata: {
      'station-7': {
        editable: true,
        name: 'station-7',
        address: '10.0.0.7',
        mac: '00:11:22:33:44:55',
        heartbeatPath: 'C:\\old\\heartbeat.json',
        credentialRef: 'station-7-credential',
      },
    },
    hostState: { 'station-7': { stale: true } },
    candidateState: {},
    getStation: key => key === 'station-8' ? station : null,
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      if (url === '/lab-admin/labs') {
        return response({ labs: [{ labId: 'lab-8', resourceType: 0, accessKey: 'guac:conn-8', accessURI: 'https://gateway.example/lab' }] });
      }
      return response({ host: { name: 'station-7-renamed' } });
    },
    provisioningController: { save: async (payload) => events.push(['provision', payload]) },
    credentialsController: { save: async (payload, button) => events.push(['credentials', payload, button]) },
    callbacks: {
      showToast: (...args) => events.push(args),
      loadHostInventory: async options => events.push(['reload', options]),
      stopHeartbeatStream: host => events.push(['stop', host]),
    },
    documentImpl: { createElement: () => ({ value: '', textContent: '' }) },
  });

  await controller.openProvision('station-8');
  await new Promise(resolve => setTimeout(resolve, 0));
  await controller.saveProvision();
  controller.openEdit('station-7');
  fields.editName.value = 'station-7-renamed';
  await controller.saveEdit();
  controller.openCredentials('station-7');
  fields.credentialPassword.value = 'secret';
  await controller.saveCredentials();

  assert.equal(fields.provisionConnectionId.value, 'conn-8');
  assert.equal(fields.provisionHostAddress.value, '10.0.0.8');
  assert.equal(controller.getState().provisionStationKey, 'station-8');
  assert.deepEqual(JSON.parse(JSON.stringify(events[0])), ['provision', {
    connectionId: 'conn-8',
    name: '10.0.0.8',
    address: '10.0.0.8',
    mac: '',
    broadcast: '',
    credentialRef: '10.0.0.8',
    labstationExe: 'C:\\Lab Station\\LabStation.exe',
    localModeFlagPath: 'C:\\Lab Station\\labstation\\data\\local-mode.flag',
    heartbeatPath: 'C:\\Lab Station\\labstation\\data\\telemetry\\heartbeat.json',
    eventsPath: 'C:\\Lab Station\\labstation\\data\\telemetry\\session-guard-events.jsonl',
  }]);
  assert.equal(requests.find(request => request.url.includes('/ops/api/hosts/')).options.method, 'PATCH');
  assert.ok(events.some(event => event[0] === 'stop' && event[1] === 'station-7'));
  assert.ok(events.some(event => event[0] === 'credentials'));
});

test('rejects editing a host that is not dynamically configured', () => {
  const module = loadModule();
  const fields = modalFields();
  const events = [];
  const controller = module.createController({
    fields,
    hostMetadata: { static: { editable: false } },
    hostState: {},
    candidateState: {},
    getStation: () => null,
    fetchImpl: async () => response({}),
    provisioningController: { save: async () => {} },
    credentialsController: { save: async () => {} },
    callbacks: { showToast: (...args) => events.push(args) },
    documentImpl: { createElement: () => ({}) },
  });

  controller.openEdit('static');

  assert.equal(fields.editModal.classList.contains?.('show') || false, false);
  assert.deepEqual(events, [['Only dynamically configured hosts can be edited', 'error']]);
});
