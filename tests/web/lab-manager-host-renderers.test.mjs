import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-host-renderers.js', repoRoot);

function loadRenderers() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-host-renderers.js',
  });
  return context.window.LabManagerHostRenderers;
}

function dependencies() {
  return {
    documentCtor: { createElement: () => ({}) },
    escapeHtml: value => String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;'),
    formatDate: value => `date:${value}`,
    formatBool: value => value === true ? 'yes' : value === false ? 'no' : 'unknown',
  };
}

test('host row renderer preserves status markup and escapes host data', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const html = renderer.renderHostRowMarkup(
    '<station>',
    {
      heartbeat: {
        timestamp: '2026-09-13T10:00:00Z',
        summary: { ready: true },
        status: { localSessionActive: false, localModeEnabled: true },
        operations: {
          lastForcedLogoff: { timestamp: '2026-09-13T09:00:00Z', user: 'operator<&' },
          lastPowerAction: { timestamp: '2026-09-13T09:30:00Z', mode: 'wake<&' },
        },
      },
    },
    {
      address: '10.0.0.1<&',
      editable: true,
      winrmConfigured: true,
      winrmTrustStatus: 'ready',
      stationPathsReady: false,
      stationPathIssues: ['should not be displayed'],
      guacamole: {
        status: 'multiple',
        connections: [
          { name: 'Station<&', protocol: 'rdp', port: 3389 },
          { hostname: 'backup', protocol: 'ssh', port: 22 },
        ],
      },
    },
  );

  assert.match(html, /class="host-title">&lt;station&gt;<\/div>/);
  assert.match(html, /Address: <span class="mono">10\.0\.0\.1&lt;&amp;<\/span>/);
  assert.match(html, /data-action="edit-host"/);
  assert.match(html, /data-action="manage-winrm-trust"/);
  assert.match(html, /class="host-status-text good">2 connections<\/span>/);
  assert.match(html, /Station&lt;&amp;/);
  assert.match(html, /date:2026-09-13T09:00:00Z - operator&lt;&amp;/);
  assert.match(html, /Ready: yes/);
  assert.match(html, />Disable Local<\/button>/);
  assert.doesNotMatch(html, /Lab Station paths/);
  assert.doesNotMatch(html, /<station>/);
});

test('host row renderer keeps missing heartbeat and trust states public', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const html = renderer.renderHostRowMarkup(
    'station-2',
    {},
    { address: '', guacamole: { status: 'none', connections: [] } },
  );

  assert.match(html, /Address: <span class="mono">n\/a<\/span>/);
  assert.match(html, /Last heartbeat: not available/);
  assert.match(html, /Forced logoff: not available/);
  assert.match(html, /Connections: <span class="host-status-text bad">No connections<\/span>/);
  assert.match(html, /WinRM credentials:[\s\S]*class="host-status-text warn">missing/);
  assert.match(html, /WinRM TLS trust:[\s\S]*class="host-status-text warn">missing/);
  assert.doesNotMatch(html, /data-action="edit-host"/);
});

test('candidate renderer preserves discovery statuses and provisioning guard', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const station = {
    key: 'host:station-3',
    address: 'station-3<&',
    nameCandidates: ['Lab<&', 'Station 3'],
    connections: [
      { protocol: 'rdp', port: 3389 },
      { protocol: 'ssh', port: 22 },
      { protocol: 'rdp', port: 3389 },
    ],
  };

  const readyHtml = renderer.renderGuacamoleCandidateRowMarkup(
    station,
    { status: 'winrm-reachable', detail: 'Open port<&' },
  );
  assert.match(readyHtml, /class="pill warn">Lab Station: WinRM reachable<\/span>/);
  assert.match(readyHtml, /candidate-station-detail">Open port&lt;&amp;/);
  assert.match(readyHtml, /Protocol \/ port: rdp:3389, ssh:22/);
  assert.match(readyHtml, /data-action="configure-candidate"/);

  const pendingHtml = renderer.renderGuacamoleCandidateRowMarkup(
    station,
    { status: 'checking' },
  );
  assert.match(pendingHtml, /class="pill warn">Lab Station: checking\.\.\.<\/span>/);
  assert.doesNotMatch(pendingHtml, /data-action="configure-candidate"/);
});

test('candidate status helpers keep the existing provisioning boundary', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());

  assert.equal(renderer.canProvisionCandidate('labstation-detected'), true);
  assert.equal(renderer.canProvisionCandidate('winrm-reachable'), true);
  assert.equal(renderer.canProvisionCandidate('checking'), false);
  assert.equal(renderer.formatDiscoveryStatus('no-response'), 'no response');
  assert.equal(renderer.formatDiscoveryStatus('unknown'), 'not checked');
  assert.equal(renderer.discoveryStatusClass('error'), 'bad');
  assert.equal(renderer.discoveryStatusClass('unknown'), 'soft');
});
