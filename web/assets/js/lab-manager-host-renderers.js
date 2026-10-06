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
            const status = String(meta.managementTrust?.status || meta.winrmTrustStatus || '').trim().toLowerCase()
                || (meta.managementTrust?.configured === true || meta.winrmTrustConfigured === true ? 'ready' : 'missing');
            const states = {
                missing: { label: 'missing', className: 'warn' },
                ready: { label: 'ready', className: 'good' },
                expired: { label: 'expired', className: 'bad' },
                'not-yet-valid': { label: 'not yet valid', className: 'bad' },
                invalid: { label: 'invalid', className: 'bad' },
            };
            return states[status] || { label: 'unavailable', className: 'warn' };
        }

        function normalizeFmuMatchValue(value) {
            return String(value || '').trim().replace(/\.$/, '').toLowerCase();
        }

        function getFmuStationDisplay(host, meta, state = {}) {
            const targetHost = normalizeFmuMatchValue(state.stationHost);
            const targetAddress = normalizeFmuMatchValue(state.stationAddress);
            const hostName = normalizeFmuMatchValue(host);
            const address = normalizeFmuMatchValue(meta.address);
            const isTarget = Boolean(targetHost && hostName === targetHost)
                || Boolean(targetAddress && address === targetAddress);
            const linked = state.linked === true
                || state.runner?.stationAuthenticated === true;
            const linkStatus = state.linkStatus
                || (linked ? 'linked' : typeof state.linked === 'boolean' ? 'unlinked' : 'unknown');
            const busy = Boolean(state.busyHost);

            if (state.configured !== true) {
                return {
                    statusLabel: 'unavailable',
                    className: 'warn',
                    action: 'link-fmu',
                    actionLabel: 'Link FMU token',
                    disabled: true,
                    title: 'Configure the Gateway FMU Station before linking a token',
                };
            }
            if (linkStatus === 'unknown') {
                return {
                    statusLabel: 'verification unavailable',
                    className: 'warn',
                    action: 'link-fmu',
                    actionLabel: 'Link FMU token',
                    disabled: true,
                    title: 'The Gateway cannot verify the current FMU token link',
                };
            }
            if (!isTarget) {
                return {
                    statusLabel: linked ? 'linked on another station' : 'not this Gateway target',
                    className: linked ? 'warn' : 'soft',
                    action: 'link-fmu',
                    actionLabel: 'Link FMU token',
                    disabled: true,
                    title: linked
                        ? 'This Gateway already has an FMU token linked to another station'
                        : 'This is not the FMU Station configured for this Gateway',
                };
            }
            if (busy) {
                return {
                    statusLabel: 'updating',
                    className: 'warn',
                    action: linked ? 'release-fmu' : 'link-fmu',
                    actionLabel: 'Updating FMU token...',
                    disabled: true,
                    title: 'FMU token operation in progress',
                };
            }
            if (linked) {
                return {
                    statusLabel: 'linked',
                    className: 'good',
                    action: 'release-fmu',
                    actionLabel: 'Release FMU token',
                    disabled: false,
                    title: 'Remove the FMU token from this station',
                };
            }
            return {
                statusLabel: 'not linked',
                className: 'warn',
                action: 'link-fmu',
                actionLabel: 'Link FMU token',
                disabled: false,
                title: 'Copy the Gateway FMU token to this station',
            };
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
            const activeEntries = Array.isArray(sessions.active)
                ? sessions.active.filter(session => session && session.active !== false
                    && !['management', 'service'].includes(session.kind))
                : null;
            const active = sessions.queryOk === false
                ? null
                : Array.isArray(activeEntries)
                    ? activeEntries.length > 0
                    : hasSummary
                        ? sessions.active
                        : localSession;
            const kindLabels = {
                'labuser-local': 'LABUSER (local)',
                'labuser-remote': 'LABUSER (remote)',
                'local-user': 'Local user',
                'remote-user': 'Remote user',
                mixed: 'LABUSER and another user',
            };
            const contractKinds = Array.isArray(activeEntries)
                ? [...new Set(activeEntries.map(session => session.kind === 'local' ? 'local-user'
                    : session.kind === 'remote' ? 'remote-user' : session.kind).filter(Boolean))]
                : [];
            const detail = active === true
                ? (contractKinds.length ? contractKinds.join(', ') : kindLabels[sessions.kind] || (legacyLocalSession ? 'local user' : 'session type unavailable'))
                : active === null
                    ? 'session status unavailable'
                    : '';
            return { active, detail };
        }

        const readinessConnectors = [
            { keys: ['physicalLab'], label: 'Physical lab' },
            { keys: ['fmu'], label: 'FMI/FMU' },
            { keys: ['opcUa', 'opc-ua', 'opcua'], label: 'OPC-UA' },
            { keys: ['tango'], label: 'TANGO' },
            { keys: ['epics'], label: 'EPICS' },
        ];

        function getReadinessIssues(entry) {
            return Array.isArray(entry?.issues)
                ? entry.issues
                    .filter(issue => typeof issue === 'string' && issue.trim())
                    .map(issue => issue.trim())
                : [];
        }

        function summarizeReadinessIssues(entry) {
            const issues = getReadinessIssues(entry);
            if (!issues.length) return 'not ready';
            const visibleIssues = issues.slice(0, 2);
            return visibleIssues.join('; ') + (issues.length > visibleIssues.length ? '; …' : '');
        }

        function getReadinessDisplay(heartbeat, summary) {
            const readiness = heartbeat.readiness && typeof heartbeat.readiness === 'object'
                ? heartbeat.readiness
                : heartbeat.status?.readiness && typeof heartbeat.status.readiness === 'object'
                    ? heartbeat.status.readiness
                    : null;
            const connectorStates = readiness
                ? readinessConnectors
                    .map(connector => {
                        const key = connector.keys.find(candidate => (
                            readiness[candidate] && typeof readiness[candidate] === 'object'
                        ));
                        const entry = key ? readiness[key] : null;
                        return entry && typeof entry.ready === 'boolean'
                            ? { ...connector, entry }
                            : null;
                    })
                    .filter(Boolean)
                : [];

            const readyConnectors = connectorStates.filter(connector => connector.entry.ready);
            if (readyConnectors.length) {
                const readyLabels = readyConnectors.map(connector => connector.label).join(' · ');
                return {
                    label: readyLabels,
                    className: 'good',
                    tooltip: readyConnectors.length < connectorStates.length
                        ? `${readyLabels} ready.`
                        : '',
                };
            }

            if (connectorStates.length) {
                return {
                    label: 'Not ready',
                    className: 'bad',
                    tooltip: connectorStates
                        .map(connector => `${connector.label}: ${summarizeReadinessIssues(connector.entry)}`)
                        .join(' '),
                };
            }

            // Older heartbeats only exposed summary.ready, which represented the
            // physical/Remote App path. Keep that legacy data meaningful while
            // using the connector vocabulary in the UI.
            const legacyReady = typeof summary.ready === 'boolean' ? summary.ready : null;
            if (legacyReady === true) {
                return { label: 'Remote app', className: 'good', tooltip: '' };
            }
            if (legacyReady === false) {
                const summaryIssues = getReadinessIssues(summary);
                return {
                    label: 'Not ready',
                    className: 'bad',
                    tooltip: summaryIssues.length
                        ? `Remote app: ${summaryIssues.slice(0, 2).join('; ')}`
                        : 'Lab Station is not ready.',
                };
            }
            return {
                label: 'Not ready',
                className: 'bad',
                tooltip: 'No connector readiness reported by Lab Station.',
            };
        }

        function renderHostRowMarkup(host, data = {}, meta = {}, fmuStationState = {}) {
            const guacamole = meta.guacamole || {};
            const heartbeat = data.heartbeat || {};
            const summary = heartbeat.summary || {};
            const status = heartbeat.status && typeof heartbeat.status === 'object'
                ? heartbeat.status
                : heartbeat.station && typeof heartbeat.station === 'object'
                    ? heartbeat.station
                    : heartbeat;
            const topLevelOperations = heartbeat.operations && typeof heartbeat.operations === 'object'
                ? heartbeat.operations
                : null;
            const statusOperations = status.operations && typeof status.operations === 'object'
                ? status.operations
                : null;
            const operations = topLevelOperations && Object.keys(topLevelOperations).length
                ? topLevelOperations
                : statusOperations || topLevelOperations || {};
            const transport = String(meta.managementTransport || 'winrm').toLowerCase();
            const transportLabel = transport === 'ssh' ? 'SSH' : 'WinRM';
            const platformLabel = String(meta.platform || (transport === 'ssh' ? 'linux' : 'windows')).toUpperCase();
            const credentialsConfigured = meta.managementCredentials?.configured === true
                || (transport === 'winrm' && Boolean(meta.winrmConfigured));
            const readiness = getReadinessDisplay(heartbeat, summary);
            const localSession = status.localSessionActive;
            const activeSessionDisplay = getActiveSessionDisplay(status, localSession);
            const activeSession = activeSessionDisplay.active;
            const localMode = typeof status.localModeEnabled === 'boolean'
                ? status.localModeEnabled : heartbeat.localModeEnabled;
            const lastForced = operations.lastForcedLogoff;
            const lastPower = operations.lastPowerAction;
            const updated = heartbeat.timestamp;
            const hasHeartbeat = Boolean(updated);
            const winrmTrust = getWinrmTrustDisplay(meta);
            const fmuStation = getFmuStationDisplay(host, meta, fmuStationState);

            const safeHost = escapeHtml(host);
            const safeAddress = escapeHtml(meta.address) || 'n/a';
            const canEdit = meta.editable === true;
            const safeUpdated = escapeHtml(formatHostDate(updated, hasHeartbeat));
            const safeLastForced = escapeHtml(formatLastForcedLogoff(lastForced, hasHeartbeat));
            const safeLastPower = escapeHtml(formatLastPowerAction(lastPower, hasHeartbeat));
            const safeReadinessLabel = escapeHtml(readiness.label);
            const safeReadinessTooltip = escapeHtml(readiness.tooltip);
            const readinessTooltipClass = readiness.className === 'good'
                ? ' ready-indicator-tooltip-good'
                : '';
            const readinessTooltipId = 'readiness-tooltip-'
                + String(host).replace(/[^A-Za-z0-9_-]/g, '-');
            const readinessTooltipMarkup = readiness.tooltip
                ? ` title="${safeReadinessTooltip}" tabindex="0" aria-describedby="${readinessTooltipId}" aria-label="${safeReadinessLabel}. ${safeReadinessTooltip}"`
                : '';
            const readinessExplanationMarkup = readiness.tooltip
                ? `<span class="ready-indicator-tooltip${readinessTooltipClass}" id="${readinessTooltipId}" role="tooltip">${safeReadinessTooltip}</span>`
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
            const fmuActionDisabled = fmuStation.disabled ? ' disabled' : '';

            return `
            <div>
                <div class="host-title-row">
                    <div class="host-title">${safeHost}</div>
                    ${canEdit ? '<button class="host-edit-btn" data-action="edit-host" title="Edit host" aria-label="Edit host"><svg class="host-edit-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"></path></svg></button>' : ''}
                </div>
                <div class="host-meta host-address">Address: <span class="mono">${safeAddress}</span></div>
                <div class="host-meta">Connections: ${guacamoleStatusMarkup}</div>
                <div class="host-meta">Platform: ${escapeHtml(platformLabel)} · Station contract: ${escapeHtml(meta.contractVersion || 'unknown')}</div>
                <div class="host-meta">Management: ${escapeHtml(transportLabel)}:${escapeHtml(meta.managementPort || (transport === 'ssh' ? 22 : 5986))}</div>
                <div class="host-meta">${escapeHtml(transportLabel)} credentials: <button type="button" class="host-status-action" data-action="set-winrm-credentials" title="Set or update ${escapeHtml(transportLabel)} management credentials" aria-label="Set or update ${escapeHtml(transportLabel)} management credentials"><span class="host-status-text ${credentialsConfigured ? 'good' : 'warn'}">${credentialsConfigured ? 'configured' : 'missing'}</span></button></div>
                <div class="host-meta">${escapeHtml(transport === 'ssh' ? 'SSH host-key trust' : 'WinRM TLS trust')}: <button type="button" class="host-status-action" data-action="manage-winrm-trust" title="Manage ${escapeHtml(transportLabel)} trust" aria-label="Manage ${escapeHtml(transportLabel)} trust"><span class="host-status-text ${winrmTrust.className}">${escapeHtml(winrmTrust.label)}</span></button></div>
            </div>
            <div class="host-state-column">
                <div class="host-meta host-state" aria-label="Current station state">
                    <span class="pill ${readiness.className}${readiness.tooltip ? ' ready-indicator' : ''}"${readinessTooltipMarkup}>${safeReadinessLabel}${readinessExplanationMarkup}</span>
                    <span class="pill ${activeSession === true ? 'warn' : 'soft'}${activeSessionDisplay.detail ? ' active-session-indicator' : ''}"${activeSessionTooltipMarkup}>Active session: ${formatBool(activeSession)}${activeSessionExplanationMarkup}</span>
                    <span class="pill ${localMode === true ? 'warn' : 'soft'}">Local mode: ${formatBool(localMode)}</span>
                </div>
                <div class="host-meta host-history">
                    <span class="host-history-label">Last activity:</span>
                    <span class="host-history-items">
                        <span class="host-history-item host-history-heartbeat">Heartbeat: ${safeUpdated}</span>
                        <span class="host-history-item">Forced logoff: ${safeLastForced}</span>
                        <span class="host-history-item">Power action: ${safeLastPower}</span>
                    </span>
                </div>
            </div>
            <div class="host-actions">
                <button class="mini-btn" data-action="poll" title="Check station status">Heartbeat</button>
                <button class="mini-btn" data-action="wake-ops" title="Configure Wake Ops and wake station">Wake Ops</button>
                <button class="mini-btn primary" data-action="prepare" title="Prepare station">Prepare</button>
                <button class="mini-btn" data-action="release" title="Release station">Release</button>
                <button class="mini-btn danger" data-action="shutdown" title="Shut down station">Shutdown</button>
                <button class="mini-btn secondary" data-action="toggle-local-mode" title="${localMode ? 'Disable' : 'Enable'} local mode">${localMode ? 'Disable' : 'Enable'} Local</button>
                <button class="mini-btn${fmuStation.action === 'release-fmu' ? ' danger' : ''}" data-action="${fmuStation.action}" title="${fmuStation.title}"${fmuActionDisabled}>${fmuStation.actionLabel}</button>
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
            return status === 'labstation-detected' || status === 'winrm-reachable'
                || status === 'management-trust-pending';
        }

        function formatDiscoveryStatus(status) {
            if (status === 'labstation-detected') return 'detected';
            if (status === 'winrm-reachable') return 'WinRM reachable';
            if (status === 'management-trust-pending') return 'SSH reachable · trust pending';
            if (status === 'host-resolves') return 'host resolves';
            if (status === 'no-response') return 'no response';
            if (status === 'checking') return 'checking...';
            if (status === 'error') return 'check failed';
            return 'not checked';
        }

        function discoveryStatusClass(status) {
            if (status === 'labstation-detected') return 'good';
            if (status === 'winrm-reachable' || status === 'management-trust-pending' || status === 'host-resolves' || status === 'checking') return 'warn';
            if (status === 'no-response' || status === 'error') return 'bad';
            return 'soft';
        }

        function renderGuacamoleCandidateRowMarkup(station, state = {}) {
            const safeName = escapeHtml(station.address || station.nameCandidates[0] || 'Unnamed station');
            const safeConnections = escapeHtml(station.nameCandidates.join(', ') || 'Unnamed connection');
            const connectionSummary = station.connections
                .map(connection => `${connection.protocol || 'unknown'}:${connection.port || 'n/a'}`)
                .filter((value, index, values) => values.indexOf(value) === index)
                .join(', ');
            const safeProtocol = escapeHtml(connectionSummary || 'unknown');
            const statusText = formatDiscoveryStatus(state.status);
            const statusClass = discoveryStatusClass(state.status);

            return `
            <div>
                <div class="host-title-row">
                    <div class="host-title">${safeName}</div>
                </div>
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
