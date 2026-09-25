(function (root) {
    'use strict';

    function createController({
        documentCtor = root.document,
        escapeHtml,
        formatDate,
        formatBool,
    } = {}) {
        if (!documentCtor || typeof documentCtor.createElement !== 'function') {
            throw new Error('LabManagerHostRenderers requires document');
        }
        if (typeof escapeHtml !== 'function') {
            throw new Error('LabManagerHostRenderers requires escapeHtml');
        }
        if (typeof formatDate !== 'function') {
            throw new Error('LabManagerHostRenderers requires formatDate');
        }
        if (typeof formatBool !== 'function') {
            throw new Error('LabManagerHostRenderers requires formatBool');
        }

        function formatConnectionsStatus(connections) {
            if (!connections.length) return 'No connections';
            if (connections.length > 1) return `${connections.length} connections`;

            const connection = connections[0] || {};
            const name = connection.name || connection.hostname;
            const protocol = connection.protocol;
            if (!name) return '1 connection';
            return `1 connection - ${name}${protocol ? ` (${protocol})` : ''}`;
        }

        function connectionsStatusClass(guacamole) {
            if (guacamole.status === 'none') return 'bad';
            if (guacamole.status === 'single' || guacamole.status === 'multiple') return 'good';
            return 'soft';
        }

        function getWinrmTrustDisplay(meta) {
            const status = String(meta.winrmTrustStatus || '').trim().toLowerCase()
                || (meta.winrmTrustConfigured === true ? 'ready' : 'missing');
            const states = {
                missing: { label: 'missing', className: 'warn' },
                ready: { label: 'ready', className: 'good' },
                expired: { label: 'expired', className: 'bad' },
                'not-yet-valid': { label: 'not yet valid', className: 'bad' },
                invalid: { label: 'invalid', className: 'bad' },
            };
            return states[status] || { label: 'unavailable', className: 'warn' };
        }

        function formatHostDate(value, hasHeartbeat) {
            return value ? formatDate(value) : hasHeartbeat ? 'never' : 'not available';
        }

        function formatLastForcedLogoff(info, hasHeartbeat) {
            if (!info || !info.timestamp) return hasHeartbeat ? 'never' : 'not available';
            const parts = [formatDate(info.timestamp)];
            if (info.user) parts.push(info.user);
            return parts.join(' - ');
        }

        function formatLastPowerAction(info, hasHeartbeat) {
            if (!info || (!info.timestamp && !info.mode)) return hasHeartbeat ? 'never' : 'not available';
            const parts = [];
            if (info.mode) parts.push(info.mode);
            if (info.timestamp) parts.push(formatDate(info.timestamp));
            return parts.join(' - ');
        }

        function getActiveSessionDisplay(status, localSession) {
            const sessions = status.sessions && typeof status.sessions === 'object'
                ? status.sessions
                : {};
            const hasSummary = Object.prototype.hasOwnProperty.call(sessions, 'active');
            const legacyLocalSession = !hasSummary && localSession === true;
            const active = sessions.queryOk === false
                ? null
                : hasSummary
                    ? sessions.active
                    : localSession;
            const kindLabels = {
                'labuser-local': 'LABUSER (local)',
                'labuser-remote': 'LABUSER (remote)',
                'local-user': 'local user',
                'remote-user': 'remote user',
                mixed: 'mixed: LABUSER and another user',
            };
            const detail = active === true
                ? (kindLabels[sessions.kind] || (legacyLocalSession ? 'local user' : 'session type unavailable'))
                : active === null
                    ? 'session status unavailable'
                    : '';
            return { active, detail };
        }

        function getReadinessDisplay(heartbeat, summary) {
            const readiness = heartbeat.readiness && typeof heartbeat.readiness === 'object'
                ? heartbeat.readiness
                : heartbeat.status?.readiness && typeof heartbeat.status.readiness === 'object'
                    ? heartbeat.status.readiness
                    : null;
            const capabilities = [
                { key: 'physicalLab', label: 'Physical lab' },
                { key: 'fmu', label: 'FMU executor' },
            ].map(capability => ({
                ...capability,
                value: readiness?.[capability.key],
            }));
            const hasCapabilityReadiness = capabilities.every(capability => (
                capability.value && typeof capability.value.ready === 'boolean'
            ));

            if (!hasCapabilityReadiness) {
                const ready = summary.ready;
                return {
                    label: formatBool(ready),
                    className: ready === true ? 'good' : ready === false ? 'bad' : 'soft',
                    tooltip: '',
                };
            }

            const readyCount = capabilities.filter(capability => capability.value.ready).length;
            const state = readyCount === capabilities.length
                ? 'yes'
                : readyCount === 0
                    ? 'no'
                    : 'partial';
            const missing = capabilities
                .filter(capability => !capability.value.ready)
                .map(capability => {
                    const issues = Array.isArray(capability.value.issues)
                        ? capability.value.issues.filter(issue => typeof issue === 'string' && issue.trim())
                        : [];
                    return `${capability.label}: ${issues.length ? issues.join('; ') : 'not ready'}`;
                });
            const physicalLab = capabilities.find(capability => capability.key === 'physicalLab');
            const fmu = capabilities.find(capability => capability.key === 'fmu');
            let tooltip = '';
            if (physicalLab.value.ready && !fmu.value.ready) {
                const fmuIssues = Array.isArray(fmu.value.issues)
                    ? fmu.value.issues.filter(issue => typeof issue === 'string' && issue.trim())
                    : [];
                const reason = fmuIssues.length ? fmuIssues.join('; ') : 'the FMU executor is not ready';
                tooltip = `OK for physical labs; FMI simulations are unavailable because ${reason}.`;
            } else if (!physicalLab.value.ready && fmu.value.ready) {
                const physicalLabIssues = Array.isArray(physicalLab.value.issues)
                    ? physicalLab.value.issues.filter(issue => typeof issue === 'string' && issue.trim())
                    : [];
                const reason = physicalLabIssues.length
                    ? physicalLabIssues.join('; ')
                    : 'the physical lab is not ready';
                tooltip = `FMI simulations are OK; physical labs are unavailable because ${reason}.`;
            } else {
                tooltip = `Partial readiness: ${missing.join(' | ')}`;
            }

            return {
                label: state,
                className: state === 'yes' ? 'good' : state === 'no' ? 'bad' : 'warn',
                tooltip: state === 'partial' ? tooltip : '',
            };
        }

        function renderHostRowMarkup(host, data = {}, meta = {}) {
            const guacamole = meta.guacamole || {};
            const heartbeat = data.heartbeat || {};
            const summary = heartbeat.summary || {};
            const status = heartbeat.status || {};
            const operations = heartbeat.operations || {};
            const winrmConfigured = Boolean(meta.winrmConfigured);
            const readiness = getReadinessDisplay(heartbeat, summary);
            const localSession = status.localSessionActive;
            const activeSessionDisplay = getActiveSessionDisplay(status, localSession);
            const activeSession = activeSessionDisplay.active;
            const localMode = status.localModeEnabled;
            const lastForced = operations.lastForcedLogoff;
            const lastPower = operations.lastPowerAction;
            const updated = heartbeat.timestamp;
            const hasHeartbeat = Boolean(updated);
            const winrmTrust = getWinrmTrustDisplay(meta);

            const safeHost = escapeHtml(host);
            const safeAddress = escapeHtml(meta.address) || 'n/a';
            const canEdit = meta.editable === true;
            const safeUpdated = escapeHtml(formatHostDate(updated, hasHeartbeat));
            const safeLastForced = escapeHtml(formatLastForcedLogoff(lastForced, hasHeartbeat));
            const safeLastPower = escapeHtml(formatLastPowerAction(lastPower, hasHeartbeat));
            const safeReadinessTooltip = escapeHtml(readiness.tooltip);
            const readinessTooltipId = 'readiness-tooltip-'
                + String(host).replace(/[^A-Za-z0-9_-]/g, '-');
            const readinessTooltipMarkup = readiness.tooltip
                ? ` title="${safeReadinessTooltip}" tabindex="0" aria-describedby="${readinessTooltipId}" aria-label="Ready: partial. ${safeReadinessTooltip}"`
                : '';
            const readinessExplanationMarkup = readiness.tooltip
                ? `<span class="ready-indicator-tooltip" id="${readinessTooltipId}" role="tooltip">${safeReadinessTooltip}</span>`
                : '';
            const activeSessionDetail = escapeHtml(activeSessionDisplay.detail);
            const activeSessionTooltipId = 'active-session-tooltip-'
                + String(host).replace(/[^A-Za-z0-9_-]/g, '-');
            const activeSessionTooltipMarkup = activeSessionDisplay.detail
                ? ` title="${activeSessionDetail}" tabindex="0" aria-describedby="${activeSessionTooltipId}" aria-label="Active session: ${escapeHtml(formatBool(activeSession))}. ${activeSessionDetail}"`
                : '';
            const activeSessionExplanationMarkup = activeSessionDisplay.detail
                ? `<span class="active-session-tooltip" id="${activeSessionTooltipId}" role="tooltip">${activeSessionDetail}</span>`
                : '';
            const guacamoleConnections = Array.isArray(guacamole.connections) ? guacamole.connections : [];
            const safeConnections = escapeHtml(formatConnectionsStatus(guacamoleConnections));
            const connectionsClass = connectionsStatusClass(guacamole);
            const hasGuacamoleMatchDetails = guacamoleConnections.length > 1;
            const guacamoleDetailsId = 'guacamole-matches-'
                + String(host).replace(/[^A-Za-z0-9_-]/g, '-');
            const guacamoleMatchMarkup = hasGuacamoleMatchDetails
                ? guacamoleConnections.map((connection, index) => {
                    const safeName = escapeHtml(
                        connection?.name || connection?.hostname || 'Connection ' + (index + 1),
                    );
                    const safeProtocol = escapeHtml(connection?.protocol || 'unknown');
                    const safePort = escapeHtml(connection?.port || 'n/a');
                    return '<div class="guacamole-match-item">'
                        + '<strong class="guacamole-match-name">' + safeName + '</strong>'
                        + '<span class="guacamole-match-meta">' + safeProtocol + ' · Port: ' + safePort + '</span>'
                        + '</div>';
                }).join('')
                : '';
            const guacamoleStatusMarkup = hasGuacamoleMatchDetails
                ? '<span class="guacamole-match-trigger" tabindex="0"'
                    + ' aria-describedby="' + escapeHtml(guacamoleDetailsId) + '">'
                    + '<span class="host-status-text ' + connectionsClass + '">' + safeConnections + '</span>'
                    + '<span class="guacamole-match-popover" id="' + escapeHtml(guacamoleDetailsId) + '" role="tooltip">'
                    + '<span class="guacamole-match-details-title">Connections for this station</span>'
                    + guacamoleMatchMarkup
                    + '</span></span>'
                : '<span class="host-status-text ' + connectionsClass + '">' + safeConnections + '</span>';

            return `
            <div>
                <div class="host-title-row">
                    <div class="host-title">${safeHost}</div>
                    ${canEdit ? '<button class="host-edit-btn" data-action="edit-host" title="Edit host" aria-label="Edit host"><svg class="host-edit-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"></path></svg></button>' : ''}
                </div>
                <div class="host-meta host-address">Address: <span class="mono">${safeAddress}</span></div>
                <div class="host-meta">Last heartbeat: ${safeUpdated}</div>
                <div class="host-meta">Connections: ${guacamoleStatusMarkup}</div>
                <div class="host-meta">WinRM credentials: <button type="button" class="host-status-action" data-action="set-winrm-credentials" title="Set or update WinRM credentials" aria-label="Set or update WinRM credentials"><span class="host-status-text ${winrmConfigured ? 'good' : 'warn'}">${winrmConfigured ? 'configured' : 'missing'}</span></button></div>
                <div class="host-meta">WinRM TLS trust: <button type="button" class="host-status-action" data-action="manage-winrm-trust" title="Manage WinRM TLS trust" aria-label="Manage WinRM TLS trust"><span class="host-status-text ${winrmTrust.className}">${winrmTrust.label}</span></button></div>
            </div>
            <div class="host-state-column">
                <div class="host-meta host-state" aria-label="Current station state">
                    <span class="pill ${readiness.className}${readiness.tooltip ? ' ready-indicator' : ''}"${readinessTooltipMarkup}>Ready: ${readiness.label}${readinessExplanationMarkup}</span>
                    <span class="pill ${activeSession === true ? 'warn' : 'soft'}${activeSessionDisplay.detail ? ' active-session-indicator' : ''}"${activeSessionTooltipMarkup}>Active session: ${formatBool(activeSession)}${activeSessionExplanationMarkup}</span>
                    <span class="pill ${localMode === true ? 'warn' : 'soft'}">Local mode: ${formatBool(localMode)}</span>
                </div>
                <div class="host-meta host-history">
                    <span class="host-history-label">Last activity:</span>
                    <span class="host-history-items">
                        <span class="host-history-item">Forced logoff: ${safeLastForced}</span>
                        <span class="host-history-item">Power action: ${safeLastPower}</span>
                    </span>
                </div>
            </div>
            <div class="host-actions">
                <button class="mini-btn" data-action="poll">Heartbeat</button>
                <button class="mini-btn" data-action="wol">Wake</button>
                <button class="mini-btn primary" data-action="prepare">Prepare</button>
                <button class="mini-btn" data-action="release">Release</button>
                <button class="mini-btn danger" data-action="shutdown">Shutdown</button>
                <button class="mini-btn secondary" data-action="toggle-local-mode">${localMode ? 'Disable' : 'Enable'} Local</button>
                <button class="mini-btn" data-action="sync-aas" title="Sync Digital Twin metadata to BaSyx AAS server">Sync AAS</button>
            </div>
        `;
        }

        function buildHostRow(host, data, meta) {
            const row = documentCtor.createElement('div');
            row.className = 'host-row';
            row.dataset.host = host;
            row.innerHTML = renderHostRowMarkup(host, data, meta);
            return row;
        }

        function canProvisionCandidate(status) {
            return status === 'labstation-detected' || status === 'winrm-reachable';
        }

        function formatDiscoveryStatus(status) {
            if (status === 'labstation-detected') return 'detected';
            if (status === 'winrm-reachable') return 'WinRM reachable';
            if (status === 'host-resolves') return 'host resolves';
            if (status === 'no-response') return 'no response';
            if (status === 'checking') return 'checking...';
            if (status === 'error') return 'check failed';
            return 'not checked';
        }

        function discoveryStatusClass(status) {
            if (status === 'labstation-detected') return 'good';
            if (status === 'winrm-reachable' || status === 'host-resolves' || status === 'checking') return 'warn';
            if (status === 'no-response' || status === 'error') return 'bad';
            return 'soft';
        }

        function renderGuacamoleCandidateRowMarkup(station, state = {}) {
            const safeName = escapeHtml(station.address || station.nameCandidates[0] || 'Unnamed station');
            const safeConnections = escapeHtml(station.nameCandidates.join(', ') || 'Unnamed connection');
            const safeHost = escapeHtml(station.address || 'n/a');
            const connectionSummary = station.connections
                .map(connection => `${connection.protocol || 'unknown'}:${connection.port || 'n/a'}`)
                .filter((value, index, values) => values.indexOf(value) === index)
                .join(', ');
            const safeProtocol = escapeHtml(connectionSummary || 'unknown');
            const statusText = formatDiscoveryStatus(state.status);
            const statusClass = discoveryStatusClass(state.status);

            return `
            <div>
                <div class="host-title">${safeName}</div>
                <div class="host-meta">Host: ${safeHost}</div>
                <div class="host-meta">Connections: ${safeConnections}</div>
                <div class="host-meta">Protocol / port: ${safeProtocol}</div>
            </div>
            <div class="candidate-station-status">
                <span class="pill ${statusClass}">Lab Station: ${escapeHtml(statusText)}</span>
                ${state.detail ? `<div class="candidate-station-detail">${escapeHtml(state.detail)}</div>` : ''}
            </div>
            <div class="host-actions">
                <button class="mini-btn primary" data-action="probe-candidate">Check Lab Station</button>
                ${canProvisionCandidate(state.status) ? '<button class="mini-btn" data-action="configure-candidate">Configure ops host</button>' : ''}
            </div>
        `;
        }

        function buildGuacamoleCandidateRow(station, candidateState = {}) {
            const row = documentCtor.createElement('div');
            row.className = 'host-row';
            row.dataset.stationKey = station.key;
            row.innerHTML = renderGuacamoleCandidateRowMarkup(
                station,
                candidateState[station.key] || {},
            );
            return row;
        }

        return Object.freeze({
            buildHostRow,
            buildGuacamoleCandidateRow,
            canProvisionCandidate,
            discoveryStatusClass,
            formatDiscoveryStatus,
            renderGuacamoleCandidateRowMarkup,
            renderHostRowMarkup,
        });
    }

    root.LabManagerHostRenderers = Object.freeze({ createController });
})(window);
