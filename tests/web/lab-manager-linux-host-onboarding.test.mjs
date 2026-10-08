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
    window: { location: { origin: 'https://gateway.example' } },
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
    hidden: false,
    classList: { add() {}, remove() {} },
    closest() { return null; },
    ...overrides,
  };
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('provisions Linux hosts with SSH settings and hides Windows installation paths', async () => {
  const module = loadModule();
  const windowsPathField = element();
  const sshPortField = element();
  const profileField = element();
  const commandField = element();
  const fields = {
    provisionModal: element(),
    provisionSaveButton: element(),
    provisionConnectionId: element(),
    provisionHostName: element(),
    provisionHostNameCandidates: element({ options: [], appendChild(child) { this.options.push(child); } }),
    provisionHostAddress: element(),
    provisionHostMac: element(),
    provisionHostBroadcast: element(),
    provisionHostPlatform: element(),
    provisionManagementPort: element({ closest: () => sshPortField }),
    provisionProfile: element({ closest: () => profileField }),
    provisionStationCommand: element({ closest: () => commandField }),
    provisionLabstationPath: element({ closest: () => windowsPathField }),
  };
  const station = {
    address: '192.0.2.40',
    nameCandidates: ['linux-40'],
    connections: [{ id: 'connection-40', hostname: '192.0.2.40' }],
  };
  const saves = [];
  const controller = module.createController({
    fields,
    candidateState: {
      'linux-40': {
        connectionId: 'connection-40',
        opsHostDraft: {
          name: 'linux-40',
          platform: 'linux',
          management: { port: 2222 },
          profile: 'fmu-only',
          station: { command: '/usr/local/bin/labstationctl' },
        },
      },
    },
    hostMetadata: {},
    hostState: {},
    getStation: () => station,
    fetchImpl: async () => response({}),
    provisioningController: { save: async payload => saves.push(payload) },
    credentialsController: { save: async () => {} },
    callbacks: { showToast() {} },
    documentImpl: { createElement: () => ({}) },
  });

  controller.openProvision('linux-40');
  await controller.saveProvision();

  assert.equal(fields.provisionHostPlatform.value, 'linux');
  assert.equal(fields.provisionManagementPort.value, 2222);
  assert.equal(fields.provisionProfile.value, 'fmu-only');
  assert.equal(fields.provisionStationCommand.value, '/usr/local/bin/labstationctl');
  assert.equal(windowsPathField.hidden, true);
  assert.equal(sshPortField.hidden, false);
  assert.deepEqual(JSON.parse(JSON.stringify(saves[0])), {
    connectionId: 'connection-40',
    name: 'linux-40',
    address: '192.0.2.40',
    mac: '',
    broadcast: '',
    credentialRef: '192.0.2.40',
    platform: 'linux',
    managementTransport: 'ssh',
    managementPort: 2222,
    profile: 'fmu-only',
    stationCommand: '/usr/local/bin/labstationctl',
    labstationPath: '',
  });
});

test('SSH onboarding generates an encrypted key and pins only an out-of-band fingerprint', async () => {
  const module = loadModule();
  const requests = [];
  const prompts = [];
  const events = [];
  const fingerprint = 'SHA256:verified-fingerprint';
  const controller = module.createController({
    fields: {},
    hostMetadata: {
      'linux-40': {
        address: '192.0.2.40',
        credentialRef: 'linux-40-key',
        managementTransport: 'ssh',
        managementPort: 2222,
        profile: 'hybrid',
      },
    },
    hostState: {},
    candidateState: {},
    getStation: () => null,
    fetchImpl: async (url, options = {}) => {
      requests.push({ url, options });
      if (url === '/ops/api/station/credentials/linux-40-key' && !options.method) {
        return response({ error: 'not found' }, 404);
      }
      if (url === '/ops/api/station/credentials/linux-40-key') {
        return response({ username: 'labstation-ops', publicKey: 'ssh-ed25519 AAAA test' }, 201);
      }
      if (url.endsWith('/trust/preview')) {
        return response({ algorithm: 'ssh-ed25519', fingerprint });
      }
      if (url.endsWith('/trust/confirm')) return response({ trusted: true });
      if (url.endsWith('/verify')) {
        return response({ reachable: true, identity: { contractVersion: '3.0.0', platform: { os: 'linux' } } });
      }
      throw new Error('unexpected request ' + url);
    },
    provisioningController: { save: async () => {} },
    credentialsController: { save: async () => {} },
    callbacks: {
      showToast: (...args) => events.push(args),
      loadHostInventory: async options => events.push(['reload', options]),
    },
    confirmImpl: () => true,
    promptImpl: (message, defaultValue) => {
      prompts.push({ message, defaultValue });
      return message.startsWith('Verify this SSH host fingerprint') ? fingerprint : 'copied-key';
    },
    documentImpl: { createElement: () => ({}) },
  });

  controller.openCredentials('linux-40');
  await new Promise(resolve => setTimeout(resolve, 0));
  controller.openTrust('linux-40');
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.deepEqual(JSON.parse(requests[1].options.body), { username: 'labstation-ops' });
  assert.match(prompts[0].message, /sudo labstationctl setup --profile hybrid --ssh-port 2222/);
  assert.equal(requests[3].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[3].options.body), { fingerprint });
  assert.equal(requests[4].url, '/ops/api/station/hosts/linux-40/verify');
  assert.ok(events.some(event => event[0] === 'SSH host key confirmed and Station v3 identity verified for linux-40'));
});
