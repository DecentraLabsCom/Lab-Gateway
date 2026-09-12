import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-notifications-config.js', repoRoot);

function createField(value = '') {
  return {
    checked: false,
    options: [],
    style: { display: '' },
    textContent: '',
    value,
    appendChild(option) {
      this.options.push(option);
    },
  };
}

function loadController() {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-config.js',
  });

  const fields = {
    enabled: createField(),
    driver: createField(),
    from: createField(),
    fromName: createField(),
    defaultTo: createField(),
    timezone: createField(),
    smtpHost: createField(),
    smtpPort: createField(),
    smtpUser: createField(),
    smtpPass: createField(),
    smtpStartTls: createField(),
    graphTenant: createField(),
    graphClientId: createField(),
    graphClientSecret: createField(),
    graphFrom: createField(),
    smtpSection: createField(),
    graphSection: createField(),
    driverSummary: createField(),
    smtpPasswordHint: createField(),
    graphClientSecretHint: createField(),
  };
  const controller = context.window.LabManagerNotificationsConfig.createController({
    fields,
    commonTimezones: ['UTC', 'Europe/Madrid'],
    browserTimezone: 'Europe/Madrid',
    createOption: (label, value) => ({ label, value }),
  });
  return { controller, fields };
}

test('hydrates notification configuration and omits blank secrets from payloads', () => {
  const { controller, fields } = loadController();

  controller.populateTimezones();
  controller.applyConfig({
    enabled: true,
    driver: 'SMTP',
    from: 'gateway@example.test',
    fromName: 'Gateway',
    defaultTo: ['ops@example.test'],
    timezone: 'UTC',
    smtp: {
      host: 'smtp.example.test',
      port: 587,
      username: 'mailer',
      startTls: false,
      passwordConfigured: true,
    },
    graph: { clientSecretConfigured: true },
  });

  assert.equal(fields.enabled.checked, true);
  assert.equal(fields.driver.value, 'SMTP');
  assert.equal(fields.smtpHost.value, 'smtp.example.test');
  assert.equal(fields.smtpPass.value, '');
  assert.equal(fields.smtpPasswordHint.textContent, 'A password is stored. Leave blank to keep it.');
  assert.equal(fields.graphClientSecretHint.textContent, 'A client secret is stored. Leave blank to keep it.');
  assert.equal(fields.smtpSection.style.display, 'block');
  assert.equal(fields.graphSection.style.display, 'none');
  assert.equal(fields.driverSummary.textContent, 'SMTP');
  assert.deepEqual(JSON.parse(JSON.stringify(controller.buildPayload())), {
    enabled: true,
    driver: 'SMTP',
    from: 'gateway@example.test',
    fromName: 'Gateway',
    defaultTo: ['ops@example.test'],
    timezone: 'UTC',
    smtp: {
      host: 'smtp.example.test',
      port: 587,
      username: 'mailer',
      startTls: false,
    },
    graph: {
      tenantId: '',
      clientId: '',
      from: '',
    },
  });
});

test('uses Graph fields and disables notifications for the NOOP driver', () => {
  const { controller, fields } = loadController();

  controller.applyConfig({
    enabled: true,
    driver: 'GRAPH',
    graph: {
      tenantId: 'tenant',
      clientId: 'client',
      from: 'graph@example.test',
    },
  });
  fields.graphClientSecret.value = 'secret';

  assert.equal(fields.graphSection.style.display, 'block');
  assert.equal(fields.smtpSection.style.display, 'none');
  assert.equal(controller.buildPayload().graph.clientSecret, 'secret');

  fields.driver.value = 'NOOP';
  controller.toggleSections();
  assert.equal(fields.enabled.checked, false);
  assert.equal(fields.smtpSection.style.display, 'none');
  assert.equal(fields.graphSection.style.display, 'none');
});