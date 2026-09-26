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
  assert.match(html, /class="pill good">Remote app/);
  assert.doesNotMatch(html, /Ready:/);
  assert.match(html, /<button class="mini-btn" data-action="poll" title="Check station status">Heartbeat<\/button>/);
  assert.match(html, /<button class="mini-btn" data-action="wol" title="Wake station">Wake<\/button>/);
  assert.match(html, /<button class="mini-btn primary" data-action="prepare" title="Prepare station">Prepare<\/button>/);
  assert.match(html, /<button class="mini-btn" data-action="release" title="Release station">Release<\/button>/);
  assert.match(html, /<button class="mini-btn danger" data-action="shutdown" title="Shut down station">Shutdown<\/button>/);
  assert.match(html, /<button class="mini-btn secondary" data-action="toggle-local-mode" title="Disable local mode">Disable Local<\/button>/);
  assert.doesNotMatch(html, /data-action="sync-aas"/);
  assert.match(html, />Disable Local<\/button>/);
  assert.doesNotMatch(html, /Lab Station paths/);
  assert.doesNotMatch(html, /<station>/);
});

test('host row renderer describes enabling local mode when it is disabled', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const html = renderer.renderHostRowMarkup('station-remote-ready', {
    heartbeat: {
      timestamp: '2026-09-13T10:00:00Z',
      summary: { ready: true },
      status: { localSessionActive: false, localModeEnabled: false },
      operations: {},
    },
  }, {});

  assert.match(html, /<button class="mini-btn secondary" data-action="toggle-local-mode" title="Enable local mode">Enable Local<\/button>/);
});

test('host row renderer links and releases the single FMU token target', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const baseMeta = { address: '192.168.1.50', winrmConfigured: true };
  const fmuState = {
    configured: true,
    stationHost: 'station-fmu',
    stationAddress: '192.168.1.50',
    linked: false,
  };

  const linkHtml = renderer.renderHostRowMarkup('station-fmu', {}, baseMeta, fmuState);
  assert.doesNotMatch(linkHtml, /FMU token:/);
  assert.match(linkHtml, /data-action="link-fmu"[^>]*>Link FMU token<\/button>/);

  const linkedHtml = renderer.renderHostRowMarkup(
    'station-fmu',
    {},
    baseMeta,
    { ...fmuState, linked: true, linkedHost: 'station-fmu' },
  );
  assert.doesNotMatch(linkedHtml, /FMU token:/);
  assert.match(linkedHtml, /data-action="release-fmu"[^>]*>Release FMU token<\/button>/);

  const otherHtml = renderer.renderHostRowMarkup(
    'station-other',
    {},
    { address: '192.168.1.51' },
    { ...fmuState, linked: true, linkedHost: 'station-fmu' },
  );
  assert.match(otherHtml, /title="This Gateway already has an FMU token linked to another station"/);
  assert.match(otherHtml, /data-action="link-fmu"[^>]* disabled>Link FMU token<\/button>/);

  const unknownHtml = renderer.renderHostRowMarkup(
    'station-fmu',
    {},
    baseMeta,
    { ...fmuState, linkStatus: 'unknown' },
  );
  assert.doesNotMatch(unknownHtml, /FMU token:/);
  assert.match(unknownHtml, /data-action="link-fmu"[^>]* disabled>Link FMU token<\/button>/);
});

test('host row renderer exposes the active session kind through an accessible tooltip', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const html = renderer.renderHostRowMarkup('station-remote-labuser', {
    heartbeat: {
      timestamp: '2026-09-13T10:00:00Z',
      summary: { ready: true },
      status: {
        localSessionActive: false,
        localModeEnabled: false,
        sessions: {
          active: true,
          kind: 'labuser-remote',
          labUserActive: true,
          labUserRemoteActive: true,
          remoteSessionActive: true,
        },
      },
      operations: {},
    },
  }, {});

  assert.match(html, /Active session: yes/);
  assert.match(html, /class="[^"]*active-session-indicator/);
  assert.match(html, /class="active-session-tooltip"[^>]*role="tooltip">LABUSER \(remote\)/);
  assert.match(html, /aria-describedby="active-session-tooltip-station-remote-labuser"/);
});

test('host row renderer keeps legacy local-session heartbeats understandable', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const html = renderer.renderHostRowMarkup('station-legacy', {
    heartbeat: {
      timestamp: '2026-09-13T10:00:00Z',
      summary: { ready: true },
      status: { localSessionActive: true, localModeEnabled: false },
      operations: {},
    },
  }, {});

  assert.match(html, /Active session: yes/);
  assert.match(html, /role="tooltip">local user<\/span>/);
});

test('host row renderer shows concrete connector states and scoped readiness reasons', () => {
  const module = loadRenderers();
  const renderer = module.createController(dependencies());
  const base = {
    timestamp: '2026-09-13T10:00:00Z',
    summary: { ready: false },
    status: { localSessionActive: false, localModeEnabled: false },
    operations: {},
  };

  const remoteAppHtml = renderer.renderHostRowMarkup('station-remote-app', {
    heartbeat: {
      ...base,
      readiness: {
        physicalLab: { ready: true, issues: [] },
        fmu: { ready: false, issues: ['FMU executor is not running'] },
      },
    },
  }, {});
  assert.match(remoteAppHtml, /class="pill good ready-indicator"[^>]*>Remote app/);
  assert.match(
    remoteAppHtml,
    /Remote app ready\./,
  );
  assert.doesNotMatch(remoteAppHtml, /FMI\/FMU|FMU executor is not running/);
  assert.doesNotMatch(remoteAppHtml, /Ready:/);
  assert.match(remoteAppHtml, /role="tooltip"/);

  const fmuHtml = renderer.renderHostRowMarkup('station-fmu', {
    heartbeat: {
      ...base,
      readiness: {
        physicalLab: { ready: false, issues: ['WinRM not ready'] },
        fmu: { ready: true, issues: [] },
      },
    },
  }, {});
  assert.match(fmuHtml, /class="pill good ready-indicator"[^>]*>FMI\/FMU/);
  assert.match(fmuHtml, /FMI\/FMU ready\./);
  assert.doesNotMatch(fmuHtml, /Remote app: WinRM not ready/);
  assert.doesNotMatch(fmuHtml, /Ready:/);

  const allConnectorsHtml = renderer.renderHostRowMarkup('station-all-connectors', {
    heartbeat: {
      ...base,
      summary: { ready: true },
      readiness: {
        physicalLab: { ready: true, issues: [] },
        fmu: { ready: true, issues: [] },
      },
    },
  }, {});
  assert.match(allConnectorsHtml, /class="pill good">Remote app · FMI\/FMU/);
  assert.doesNotMatch(allConnectorsHtml, /ready-indicator-tooltip/);

  const opcUaHtml = renderer.renderHostRowMarkup('station-opc-ua', {
    heartbeat: {
      ...base,
      readiness: {
        opcUa: { ready: true, issues: [] },
      },
    },
  }, {});
  assert.match(opcUaHtml, /class="pill good">OPC-UA/);

  const unavailableHtml = renderer.renderHostRowMarkup('station-unavailable', {
    heartbeat: {
      ...base,
      readiness: {
        physicalLab: { ready: false, issues: ['WinRM not ready'] },
        fmu: { ready: false, issues: ['FMU executor is not running'] },
      },
    },
  }, {});
  assert.match(unavailableHtml, /class="pill bad ready-indicator"[^>]*>Not ready/);
  assert.match(
    unavailableHtml,
    /Remote app: WinRM not ready FMI\/FMU: FMU executor is not running/,
  );
  assert.doesNotMatch(unavailableHtml, /Ready:/);
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
  assert.match(html, /Heartbeat: not available/);
  assert.doesNotMatch(html, /Last heartbeat:/);
  assert.match(html, /Last activity:[\s\S]*Forced logoff: not available[\s\S]*Power action: not available[\s\S]*Heartbeat: not available/);
  assert.doesNotMatch(html, /<div class="host-meta host-history">\s*<span class="host-history-item">Heartbeat:/);
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
