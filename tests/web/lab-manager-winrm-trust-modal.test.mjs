import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-winrm-trust-modal.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: { confirm: () => true } });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-winrm-trust-modal.js',
  });
  return context.window.LabManagerWinrmTrustModal;
}

function element() {
  const classes = new Set();
  return {
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    textContent: '',
    className: '',
    files: [],
    children: [],
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      contains: name => classes.has(name),
    },
    replaceChildren(...children) { this.children = children; },
    appendChild(child) { this.children.push(child); return child; },
    append(...children) { this.children.push(...children); },
  };
}

function fields() {
  return {
    modal: element(),
    modalHost: element(),
    current: element(),
    certificate: element(),
    certificateName: element(),
    preview: element(),
    previewDetails: element(),
    fingerprintConfirmed: element(),
    previewButton: element(),
    saveButton: element(),
    verifyButton: element(),
    deleteButton: element(),
  };
}

test('keeps WinRM trust modal rendering and save guards inside its controller', async () => {
  const module = loadModule();
  const modalFields = fields();
  const elements = [];
  const events = [];
  const controller = module.createController({
    fields: modalFields,
    hostMetadata: { 'station-1': { address: '10.0.0.7', winrmConfigured: true } },
    trustController: {
      load: async host => events.push(['load', host]),
      preview: async (...args) => events.push(['preview', ...args]),
      save: async (...args) => events.push(['save', ...args]),
      remove: async host => events.push(['remove', host]),
    },
    pollHeartbeat: async host => events.push(['heartbeat', host]),
    formatDate: value => `date:${value}`,
    showToast: (...args) => events.push(args),
    confirmImpl: () => true,
    documentImpl: {
      createElement: tag => {
        const created = element();
        created.tagName = tag;
        elements.push(created);
        return created;
      },
    },
  });

  await controller.open('station-1');
  controller.renderState({ status: 'ready', fingerprintSha256: 'sha256', notAfter: 'tomorrow' });
  modalFields.certificate.files = [{ name: 'station.pem' }];
  controller.handleCertificateSelected();
  controller.renderPreview({ status: 'ready', valid: true, fingerprintSha256: 'sha256' });
  modalFields.fingerprintConfirmed.checked = true;
  controller.updateSaveState();
  await controller.save();

  assert.equal(modalFields.modal.classList.contains('show'), true);
  assert.equal(modalFields.modalHost.textContent, 'Host: station-1 · Address: 10.0.0.7');
  assert.equal(modalFields.current.children[0].textContent, 'Current trust: ready');
  assert.equal(modalFields.certificateName.textContent, 'station.pem');
  assert.equal(modalFields.saveButton.disabled, true);
  assert.deepEqual(events.at(-1), ['save', 'station-1', modalFields.certificate.files[0], {
    status: 'ready', valid: true, fingerprintSha256: 'sha256',
  }]);
  assert.ok(elements.length > 0);
});

test('does not verify or delete trust without an active configured host', async () => {
  const module = loadModule();
  const modalFields = fields();
  const events = [];
  const controller = module.createController({
    fields: modalFields,
    hostMetadata: {},
    trustController: { remove: async host => events.push(['remove', host]) },
    pollHeartbeat: async host => events.push(['heartbeat', host]),
    showToast: (...args) => events.push(args),
    confirmImpl: () => true,
    documentImpl: { createElement: () => element() },
  });

  await controller.verify();
  await controller.delete();

  assert.deepEqual(events, []);
});
