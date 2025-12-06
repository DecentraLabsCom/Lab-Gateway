// Utility function to escape HTML and prevent XSS attacks
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    const driverEl = $('#driver');
    const enabledEl = $('#enabled');
    const fromEl = $('#from');
    const fromNameEl = $('#fromName');
    const defaultToEl = $('#defaultTo');
    const timezoneEl = $('#timezone');
    const COMMON_TIMEZONES = [
        'UTC',
        'Europe/Madrid', 'Europe/London', 'Europe/Berlin', 'Europe/Paris',
        'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
        'America/Mexico_City', 'America/Sao_Paulo', 'America/Bogota',
        'Africa/Johannesburg', 'Africa/Cairo',
        'Asia/Dubai', 'Asia/Kolkata', 'Asia/Shanghai', 'Asia/Tokyo',
        'Australia/Sydney'
    ];
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

    const smtpHostEl = $('#smtpHost');
    const smtpPortEl = $('#smtpPort');
    const smtpUserEl = $('#smtpUser');
    const smtpPassEl = $('#smtpPass');
    const smtpStartTlsEl = $('#smtpStartTls');

    const graphTenantEl = $('#graphTenant');
    const graphClientIdEl = $('#graphClientId');
    const graphClientSecretEl = $('#graphClientSecret');
    const graphFromEl = $('#graphFrom');
    const driverSummary = $('#driverSummary');

    // Auth/health elements
    const authStatusPill = $('#authStatusPill');
    const authRefreshBtn = $('#authRefreshBtn');
    const authRpcEl = $('#authRpc');
    const authMarketplaceEl = $('#authMarketplace');
    const authPrivateKeyEl = $('#authPrivateKey');

    // Modal controls
    const modal = $('#configModal');
    const configureBtn = $('#configureBtn');
    const closeModalBtn = $('#closeModal');
    const cancelModalBtn = $('#cancelModal');

    populateTimezones();

    $('#btnTestLoad').addEventListener('click', loadConfig);
    $('#saveConfigBtn').addEventListener('click', saveConfig);
    $('#btnTestEmail').addEventListener('click', sendTestEmail);
    driverEl.addEventListener('change', toggleSections);
    configureBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);
    if (authRefreshBtn) {
        authRefreshBtn.addEventListener('click', loadAuthHealth);
    }

    loadConfig();
    loadAuthHealth();

    // Lab Station ops state
    const hostInput = $('#hostInput');
    const addHostBtn = $('#addHostBtn');
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const hostState = {};
    let hostNames = loadHosts();
    
    // Reservation timeline elements
    const timelineInput = $('#timelineReservationId');
    const timelineBtn = $('#loadTimelineBtn');
    const timelineResult = $('#timelineResult');
    const TIMELINE_DEFAULT_LIMIT = 100;
    const timelineState = {
        reservationId: null,
        limit: TIMELINE_DEFAULT_LIMIT,
        operations: [],
        base: null,
        pagination: null,
        nextOffset: 0,
        loading: false
    };
    
    if (timelineBtn && timelineInput && timelineResult) {
        timelineBtn.addEventListener('click', fetchTimeline);
        timelineInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                fetchTimeline();
            }
        });
    }

    if (addHostBtn && hostInput) {
        addHostBtn.addEventListener('click', addHost);
    }
    if (refreshHostsBtn) {
        refreshHostsBtn.addEventListener('click', refreshAllHosts);
    }
    if (hostListEl) {
        hostListEl.addEventListener('click', handleHostActions);
        renderHosts();
    }

    function loadConfig() {
        setStatus('Loading...');
        fetch('/treasury/admin/notifications', { credentials: 'include' })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                const cfg = data.config || {};
                enabledEl.checked = !!cfg.enabled;
                driverEl.value = cfg.driver || 'NOOP';
                fromEl.value = cfg.from || '';
                fromNameEl.value = cfg.fromName || '';
                defaultToEl.value = (cfg.defaultTo || []).join(', ');
                setTimezone(cfg.timezone || browserTimezone);
                if (cfg.smtp) {
                    smtpHostEl.value = cfg.smtp.host || '';
                    smtpPortEl.value = cfg.smtp.port || '';
                    smtpUserEl.value = cfg.smtp.username || '';
                    smtpPassEl.value = cfg.smtp.password || '';
                    smtpStartTlsEl.checked = cfg.smtp.startTls ?? true;
                }
                if (cfg.graph) {
                    graphTenantEl.value = cfg.graph.tenantId || '';
                    graphClientIdEl.value = cfg.graph.clientId || '';
                    graphClientSecretEl.value = cfg.graph.clientSecret || '';
                    graphFromEl.value = cfg.graph.from || '';
                }
                toggleSections();
                updateDriverSummary();
                setStatus('Loaded');
                showToast('Configuration loaded', 'success');
            })
            .catch(err => {
                console.error(err);
                setStatus('Error');
                showToast('Cannot load config (check admin access)', 'error');
            });
    }

    function saveConfig() {
        const payload = {
            enabled: enabledEl.checked,
            driver: driverEl.value,
            from: fromEl.value.trim(),
            fromName: fromNameEl.value.trim(),
            defaultTo: defaultToEl.value.split(',').map(x => x.trim()).filter(Boolean),
            timezone: timezoneEl.value,
            smtp: {
                host: smtpHostEl.value.trim(),
                port: smtpPortEl.value ? parseInt(smtpPortEl.value, 10) : null,
                username: smtpUserEl.value.trim(),
                password: smtpPassEl.value.trim(),
                startTls: smtpStartTlsEl.checked
            },
            graph: {
                tenantId: graphTenantEl.value.trim(),
                clientId: graphClientIdEl.value.trim(),
                clientSecret: graphClientSecretEl.value.trim(),
                from: graphFromEl.value.trim()
            }
        };

        fetch('/treasury/admin/notifications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(() => {
                setStatus('Saved');
                showToast('Configuration saved', 'success');
            })
            .catch(err => {
                console.error(err);
                setStatus('Error');
                showToast('Save failed (check admin access)', 'error');
            });
    }

    function toggleSections() {
        const driver = driverEl.value;
        $('#smtpSection').style.display = driver === 'SMTP' ? 'block' : 'none';
        $('#graphSection').style.display = driver === 'GRAPH' ? 'block' : 'none';
        if (driver === 'NOOP') {
            enabledEl.checked = false;
        }
    }

    function openModal() {
        modal.classList.add('show');
    }

    function closeModal() {
        modal.classList.remove('show');
        updateDriverSummary();
    }

    function updateDriverSummary() {
        const driver = driverEl.value || 'NOOP';
        driverSummary.textContent = driver;
    }

    function populateTimezones() {
        timezoneEl.innerHTML = '';
        const primary = new Option(`Auto (browser: ${browserTimezone})`, browserTimezone);
        timezoneEl.appendChild(primary);
        const unique = Array.from(new Set([browserTimezone, ...COMMON_TIMEZONES])).sort();
        unique.forEach(tz => {
            if (tz === browserTimezone) {
                return;
            }
            const opt = new Option(tz, tz);
            timezoneEl.appendChild(opt);
        });
    }

    function setTimezone(tz) {
        if (!tz) {
            timezoneEl.value = browserTimezone;
            return;
        }
        let found = false;
        for (const opt of timezoneEl.options) {
            if (opt.value === tz) {
                found = true;
                break;
            }
        }
        if (!found) {
            timezoneEl.appendChild(new Option(`${tz} (config)`, tz));
        }
        timezoneEl.value = tz;
    }

    function setStatus(text) {
        $('#configStatus').textContent = text;
    }

    function sendTestEmail() {
        fetch('/treasury/admin/notifications/test', {
            method: 'POST',
            credentials: 'include'
        })
            .then(async res => {
                const body = await res.json().catch(() => ({}));
                if (!res.ok || body.success === false) {
                    const msg = body.error || `Test failed (HTTP ${res.status})`;
                    throw new Error(msg);
                }
                showToast('Test email sent (check recipients)', 'success');
            })
            .catch(err => {
                console.error(err);
                showToast(err.message || 'Test email failed', 'error');
            });
    }

    function showToast(msg, type = 'info') {
        const toast = $('#toast');
        toast.textContent = msg;
        toast.className = `toast show ${type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
        setTimeout(() => toast.className = 'toast', 2500);
    }

    function $(sel) { return document.querySelector(sel); }

    // ---- Lab Station ops helpers ----
    function loadHosts() {
        try {
            const raw = localStorage.getItem('lab_hosts');
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.warn('Cannot parse saved hosts', e);
            return [];
        }
    }

    function saveHosts() {
        localStorage.setItem('lab_hosts', JSON.stringify(hostNames));
    }

    function addHost() {
        const value = (hostInput.value || '').trim();
        if (!value) return;
        if (!hostNames.includes(value)) {
            hostNames.push(value);
            saveHosts();
            renderHosts();
            showToast(`Host ${value} added`, 'success');
        }
        hostInput.value = '';
    }

    function removeHost(name) {
        hostNames = hostNames.filter(h => h !== name);
        delete hostState[name];
        saveHosts();
        renderHosts();
        showToast(`Host ${name} removed`, 'success');
    }

    function renderHosts() {
        if (!hostListEl) return;
        hostListEl.innerHTML = '';
        if (!hostNames.length) {
            hostListEl.innerHTML = '<div class="empty">Add a host to start polling heartbeat.</div>';
            return;
        }
        hostNames.forEach(host => {
            hostListEl.appendChild(buildHostRow(host));
        });
    }

    function buildHostRow(host) {
        const data = hostState[host] || {};
        const heartbeat = data.heartbeat || {};
        const summary = heartbeat.summary || {};
        const status = heartbeat.status || {};
        const operations = heartbeat.operations || {};
        const ready = summary.ready;
        const localSession = status.localSessionActive;
        const localMode = status.localModeEnabled;
        const lastForced = operations.lastForcedLogoff;
        const lastPower = operations.lastPowerAction;
        const updated = heartbeat.timestamp;

        // Escape all user-controlled data to prevent XSS
        const safeHost = escapeHtml(host);
        const safeUpdated = escapeHtml(updated) || 'n/a';
        const safeLastForcedTs = escapeHtml(lastForced && lastForced.timestamp) || 'n/a';
        const safeLastPowerMode = escapeHtml(lastPower && lastPower.mode);
        const safeLastPowerTs = escapeHtml(lastPower && lastPower.timestamp);
        const safeLastPower = safeLastPowerMode ? `${safeLastPowerMode} @ ${safeLastPowerTs}` : 'n/a';

        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.host = host;
        row.innerHTML = `
            <div>
                <div class="host-title">${safeHost}</div>
                <div class="host-meta">Updated: ${safeUpdated}</div>
                <div class="host-meta">Last forced logoff: ${safeLastForcedTs}</div>
                <div class="host-meta">Last power: ${safeLastPower}</div>
            </div>
            <div class="host-meta">
                <span class="pill ${ready === true ? 'good' : ready === false ? 'bad' : ''}">Ready: ${ready === undefined ? 'n/a' : ready}</span>
                <span class="pill ${localSession ? 'warn' : 'soft'}">Local session: ${localSession ? 'yes' : 'no'}</span>
                <span class="pill ${localMode ? 'warn' : 'soft'}">Local mode: ${localMode ? 'on' : 'off'}</span>
            </div>
            <div class="host-actions">
                <button class="mini-btn" data-action="poll">Heartbeat</button>
                <button class="mini-btn" data-action="wol">Wake</button>
                <button class="mini-btn primary" data-action="prepare">Prepare</button>
                <button class="mini-btn" data-action="release">Release</button>
                <button class="mini-btn danger" data-action="shutdown">Shutdown</button>
                <button class="mini-btn" data-action="remove">Remove</button>
            </div>
        `;
        return row;
    }

    function handleHostActions(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const host = btn.closest('.host-row')?.dataset.host;
        if (!host) return;
        const action = btn.dataset.action;
        if (action === 'remove') {
            removeHost(host);
            return;
        }
        if (action === 'poll') {
            pollHeartbeat(host);
            return;
        }
        if (action === 'wol') {
            triggerWol(host);
            return;
        }
        if (action === 'prepare') {
            triggerWinrm(host, 'prepare-session', ['--guard-grace=90']);
            return;
        }
        if (action === 'release') {
            triggerWinrm(host, 'release-session', ['--reboot']);
            return;
        }
        if (action === 'shutdown') {
            triggerWinrm(host, 'power', ['shutdown', '--delay=60', '--reason=Remote order']);
        }
    }

    function refreshAllHosts() {
        hostNames.forEach(pollHeartbeat);
    }

    async function pollHeartbeat(host) {
        try {
            const res = await fetch('/ops/api/heartbeat/poll', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            hostState[host] = data;
            renderHosts();
            showToast(`Heartbeat ${host} ok`, 'success');
        } catch (err) {
            console.error(err);
            showToast(`Heartbeat failed for ${host}`, 'error');
        }
    }

    async function triggerWol(host) {
        try {
            const res = await fetch('/ops/api/wol', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            showToast(`WoL ${host}: ${data.success ? 'sent' : 'failed'}`, data.success ? 'success' : 'error');
        } catch (err) {
            console.error(err);
            showToast(`WoL failed for ${host}`, 'error');
        }
    }

    async function triggerWinrm(host, command, args = []) {
        try {
            const res = await fetch('/ops/api/winrm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, command, args })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const ok = data.exit_code === 0;
            showToast(`${command} on ${host}: ${ok ? 'ok' : 'err'}`, ok ? 'success' : 'error');
        } catch (err) {
            console.error(err);
            showToast(`${command} failed on ${host}`, 'error');
        }
    }

    async function fetchTimeline() {
        if (!timelineResult || !timelineInput) return;
        const reservationId = (timelineInput.value || '').trim();
        if (!reservationId) {
            setTimelineMessage('Provide a reservation id.');
            timelineInput.focus();
            return;
        }
        resetTimelineState(reservationId);
        await requestTimelinePage(0, false);
    }

    function resetTimelineState(reservationId) {
        timelineState.reservationId = reservationId;
        timelineState.operations = [];
        timelineState.base = null;
        timelineState.pagination = null;
        timelineState.nextOffset = 0;
        timelineState.limit = TIMELINE_DEFAULT_LIMIT;
        timelineState.loading = false;
    }

    async function requestTimelinePage(offset, append) {
        if (!timelineState.reservationId || timelineState.loading) return;
        timelineState.loading = true;
        if (!append) {
            setTimelineMessage('Loading timeline...');
        }
        try {
            const params = new URLSearchParams({
                reservationId: timelineState.reservationId,
                limit: String(timelineState.limit),
                offset: String(offset)
            });
            const res = await fetch(`/ops/api/reservations/timeline?${params.toString()}`);
            const body = await res.json();
            if (!res.ok) {
                const msg = body?.error || `Unable to load timeline (HTTP ${res.status}).`;
                if (!append) {
                    setTimelineMessage(msg);
                }
                showToast(msg, 'error');
                return;
            }
            const pageOperations = Array.isArray(body.operations) ? body.operations : [];
            if (!append || !timelineState.base) {
                timelineState.operations = pageOperations;
                timelineState.base = body;
            } else {
                timelineState.operations = timelineState.operations.concat(pageOperations);
                timelineState.base = { ...timelineState.base, ...body };
            }
            timelineState.pagination = normalizePagination(
                body.pagination,
                offset,
                pageOperations.length,
                timelineState.limit
            );
            timelineState.limit = timelineState.pagination.limit;
            timelineState.nextOffset = timelineState.pagination.nextOffset;
            renderTimelineState();
            if (!append) {
                showToast('Timeline loaded', 'success');
            }
        } catch (err) {
            console.error(err);
            if (!append) {
                setTimelineMessage('Timeline request failed.');
            }
            showToast('Timeline request failed', 'error');
        } finally {
            timelineState.loading = false;
        }
    }

    function normalizePagination(pagination, offset, returned, limitFallback) {
        const limit = Math.max(1, Number(pagination?.limit) || limitFallback || TIMELINE_DEFAULT_LIMIT);
        const total = Number.isFinite(Number(pagination?.total)) ? Number(pagination.total) : offset + returned;
        const nextOffset = Number.isFinite(Number(pagination?.nextOffset)) ? Number(pagination.nextOffset) : offset + returned;
        const hasMore = typeof pagination?.hasMore === 'boolean' ? pagination.hasMore : total > nextOffset;
        const page = Number.isFinite(Number(pagination?.page)) ? Number(pagination.page) : Math.floor(offset / limit) + 1;
        const pageSize = Number.isFinite(Number(pagination?.pageSize)) ? Number(pagination.pageSize) : limit;
        return {
            limit,
            offset,
            returned,
            total,
            nextOffset,
            hasMore,
            page,
            pageSize
        };
    }

    async function loadMoreTimeline(buttonEl) {
        if (!timelineState.pagination?.hasMore || timelineState.loading) {
            return;
        }
        if (buttonEl) {
            buttonEl.disabled = true;
            buttonEl.textContent = 'Loading...';
        }
        await requestTimelinePage(timelineState.nextOffset, true);
    }

    function renderTimelineState() {
        if (!timelineResult || !timelineState.base) return;
        const payload = {
            ...timelineState.base,
            operations: [...timelineState.operations],
            pagination: timelineState.pagination
        };
        renderTimeline(payload);
    }
    
        function setTimelineMessage(message) {
            if (!timelineResult) return;
            timelineResult.classList.add('empty');
            timelineResult.textContent = message;
        }
    
        function renderTimeline(data) {
            if (!timelineResult) return;
            const summary = buildTimelineSummary(data);
            const phases = buildTimelinePhases(data.phases || {});
            const operations = buildTimelineOperations(data.operations || [], data.pagination);
            const heartbeat = buildTimelineHeartbeat(data.heartbeat, data.host);
            timelineResult.classList.remove('empty');
            timelineResult.innerHTML = summary + phases + operations + heartbeat;
            const loadMoreBtn = timelineResult.querySelector('#timelineLoadMoreBtn');
            if (loadMoreBtn) {
                loadMoreBtn.addEventListener('click', () => loadMoreTimeline(loadMoreBtn));
            }
        }
    
        function buildTimelineSummary(data) {
            const reservation = data.reservation || {};
            const host = data.host || {};
            const rows = [
                { label: 'Reservation', value: reservation.reservationId || 'n/a', mono: true },
                { label: 'Lab', value: host.labId || reservation.labId || 'n/a' },
                { label: 'Host', value: host.name || 'n/a' },
                { label: 'Status', value: reservation.status || 'unknown' },
                { label: 'Schedule', value: formatRange(reservation.start, reservation.end) },
            ];
            return `
                <div class="timeline-summary">
                    ${rows.map(row => `
                        <div>
                            <div class="label">${row.label}</div>
                            <div class="value ${row.mono ? 'mono' : ''}">${htmlEscape(row.value)}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
    
        function buildTimelinePhases(phases) {
            const config = [
                { key: 'wake', label: 'Wake' },
                { key: 'prepare', label: 'Prepare' },
                { key: 'schedulerEnd', label: 'Scheduler End' },
                { key: 'release', label: 'Release' },
                { key: 'power', label: 'Power' },
            ];
            const pills = config.map(item => {
                const phase = phases[item.key];
                if (!phase) {
                    return `<span class="pill soft">${item.label}: pending</span>`;
                }
                const cls = phase.success ? 'good' : 'bad';
                const title = buildPhaseTitle(phase);
                const status = phase.status || (phase.success ? 'ok' : 'error');
                return `<span class="pill ${cls}" title="${htmlEscape(title)}">${item.label}: ${htmlEscape(status)}</span>`;
            }).join('');
            return `
                <div class="timeline-phases">
                    <h3>Phases</h3>
                    <div class="pill-group">${pills}</div>
                </div>
            `;
        }
    
        function buildTimelineOperations(operations, pagination) {
            const steps = operations.length
                ? operations.map((op, idx) => renderTimelineStep(op, idx)).join('')
                : '<div class="timeline-step">No orchestration events captured yet.</div>';
            const paginationControls = buildTimelinePagination(pagination);
            return `
                <div class="timeline-steps">
                    <h3>Operation Log</h3>
                    ${steps}
                    ${paginationControls}
                </div>
            `;
        }

        function buildTimelinePagination(pagination) {
            if (!pagination) {
                return '';
            }
            const returned = pagination.returned || 0;
            const total = typeof pagination.total === 'number' ? pagination.total : returned;
            const start = returned ? pagination.offset + 1 : pagination.offset;
            const end = pagination.offset + returned;
            const summary = total
                ? `Showing ${start || 0}-${end} of ${total}`
                : `Showing ${returned} entr${returned === 1 ? 'y' : 'ies'}`;
            const button = pagination.hasMore
                ? '<button id="timelineLoadMoreBtn" class="mini-btn primary">Load more</button>'
                : '';
            return `
                <div class="timeline-pagination">
                    <div class="meta">${htmlEscape(summary)}</div>
                    ${button}
                </div>
            `;
        }
    
        function renderTimelineStep(op, idx) {
            const success = !!op.success;
            const status = op.status || (success ? 'success' : 'error');
            const metaParts = [formatDate(op.createdAt)];
            if (op.durationMs !== null && op.durationMs !== undefined) {
                metaParts.push(`${op.durationMs} ms`);
            }
            if (op.responseCode) {
                metaParts.push(`code ${op.responseCode}`);
            }
            const meta = metaParts.filter(Boolean).join(' · ');
            return `
                <div class="timeline-step ${success ? 'success' : 'error'}">
                    <div class="timeline-step-header">
                        <span>${htmlEscape(op.action || `Step ${idx + 1}`)}</span>
                        <span class="pill ${success ? 'good' : 'bad'}">${htmlEscape(status)}</span>
                    </div>
                    <div class="meta">${htmlEscape(meta)}</div>
                    ${op.message ? `<div class="message">${htmlEscape(op.message)}</div>` : ''}
                </div>
            `;
        }
    
        function buildTimelineHeartbeat(heartbeat, host) {
            if (!heartbeat) {
                const name = host?.name;
                const message = name ? `No heartbeat data for ${name} yet.` : 'No heartbeat data.';
                return `
                    <div class="timeline-heartbeat">
                        <h3>Heartbeat</h3>
                        <div class="muted-text">${htmlEscape(message)}</div>
                    </div>
                `;
            }
            return `
                <div class="timeline-heartbeat">
                    <h3>Heartbeat (${htmlEscape(formatDate(heartbeat.timestamp))})</h3>
                    <div class="pill-group">
                        ${renderHeartbeatPill('Ready', heartbeat.ready)}
                        ${renderHeartbeatPill('Local mode', heartbeat.localMode)}
                        ${renderHeartbeatPill('Local session', heartbeat.localSession)}
                    </div>
                    <div class="meta">Power: ${htmlEscape(renderPowerInfo(heartbeat.lastPower))}</div>
                    <div class="meta">Forced logoff: ${htmlEscape(renderLogoffInfo(heartbeat.lastForcedLogoff))}</div>
                </div>
            `;
        }
    
        function renderHeartbeatPill(label, value) {
            const state = formatBool(value);
            const cls = value === true ? 'good' : value === false ? 'soft' : 'soft';
            return `<span class="pill ${cls}">${label}: ${state}</span>`;
        }
    
        function renderPowerInfo(info) {
            if (!info || (!info.timestamp && !info.mode)) {
                return 'n/a';
            }
            const parts = [];
            if (info.mode) parts.push(info.mode);
            if (info.timestamp) parts.push(formatDate(info.timestamp));
            return parts.join(' @ ');
        }
    
        function renderLogoffInfo(info) {
            if (!info || (!info.timestamp && !info.user)) {
                return 'n/a';
            }
            const parts = [];
            if (info.user) parts.push(info.user);
            if (info.timestamp) parts.push(formatDate(info.timestamp));
            return parts.join(' · ');
        }
    
        function buildPhaseTitle(phase) {
            const parts = [];
            if (phase.createdAt) parts.push(formatDate(phase.createdAt));
            if (phase.message) parts.push(phase.message);
            return parts.join(' · ');
        }
    
        function formatRange(start, end) {
            if (!start && !end) return 'n/a';
            return `${formatDate(start)} → ${formatDate(end)}`;
        }
    
        function formatDate(value) {
            if (!value) return 'n/a';
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) {
                return value;
            }
            return date.toLocaleString();
        }
    
        function formatBool(value) {
            if (value === true) return 'yes';
            if (value === false) return 'no';
            return 'n/a';
        }
    
    function htmlEscape(value) {
        const str = (value ?? '').toString();
        return str.replace(/[&<>"'`]/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
            '`': '&#96;'
        })[ch] || ch);
    }

    // ---- Auth / blockchain-services health ----
    async function loadAuthHealth() {
        if (authStatusPill) {
            authStatusPill.textContent = 'Loading...';
            authStatusPill.className = 'pill soft';
        }
        try {
            const [blockchainResult, labsOk] = await Promise.all([
                fetch('/health', { headers: { 'Accept': 'application/json' } })
                    .then(async res => {
                        const bodyText = await res.text();
                        let data = {};
                        try {
                            data = bodyText ? JSON.parse(bodyText) : {};
                        } catch (e) {
                            data = { parseError: e.message };
                        }
                        const ok = res.ok && (data.status === 'UP' || data.status === 'DEGRADED');
                        return { ok, res, data };
                    })
                    .catch(err => ({ ok: false, error: err.message, data: null })),
                fetch('/guacamole/', { method: 'GET' })
                    .then(res => res.ok)
                    .catch(() => false)
            ]);

            const labsHealthy = labsOk === true;
            const blockchainHealthy = blockchainResult.ok === true;
            const overall = computeOverallStatus(labsHealthy, blockchainHealthy);

            renderAuthHealth({
                statusText: overall.text,
                pillClass: overall.className,
                rpcUp: blockchainResult?.data?.rpc_up,
                rpcClient: blockchainResult?.data?.rpc_client_version,
                privateKey: blockchainResult?.data?.private_key_present,
                marketplaceCached: blockchainResult?.data?.marketplace_key_cached,
                marketplaceUrl: blockchainResult?.data?.marketplace_key_url
            });
        } catch (err) {
            console.error(err);
            renderAuthHealth({
                statusText: 'System Unavailable',
                pillClass: 'bad',
                rpcUp: false,
                rpcClient: '-',
                privateKey: false,
                marketplaceCached: false,
                marketplaceUrl: ''
            });
            showToast('Auth health check failed', 'error');
        }
    }

    function renderAuthHealth(state) {
        const cls = state.pillClass || statusToClass(state.statusText);
        if (authStatusPill) {
            authStatusPill.textContent = state.statusText || 'Unknown';
            authStatusPill.className = `pill ${cls}`;
        }
        if (authRpcEl) authRpcEl.textContent = formatRpc(state.rpcUp, state.rpcClient);
        if (authMarketplaceEl) authMarketplaceEl.textContent = formatMarketplace(state.marketplaceCached, state.marketplaceUrl);
        if (authPrivateKeyEl) authPrivateKeyEl.textContent = formatPrivateKey(state.privateKey);
    }

    function computeOverallStatus(labsOk, blockchainOk) {
        const available = [];
        const missing = [];
        if (labsOk) available.push('Labs');
        else missing.push('Labs');
        if (blockchainOk) available.push('Blockchain');
        else missing.push('Blockchain');

        if (labsOk && blockchainOk) {
            return { text: 'System Online', className: 'good' };
        }
        if (labsOk || blockchainOk) {
            const missingText = missing.length ? ` (missing: ${missing.join(', ')})` : '';
            return { text: `Partial: ${available.join(', ')}${missingText}`, className: 'warn' };
        }
        return { text: 'System Unavailable (missing: Labs, Blockchain)', className: 'bad' };
    }

    function statusToClass(status) {
        const val = (status || '').toString().toUpperCase();
        if (val.startsWith('SYSTEM ONLINE')) return 'good';
        if (val.startsWith('PARTIAL')) return 'warn';
        if (val === 'UP' || val === 'HEALTHY') return 'good';
        if (val === 'DEGRADED') return 'warn';
        if (val.startsWith('HTTP')) return 'warn';
        return 'bad';
    }

    function formatRpc(up, client) {
        const state = up === undefined ? 'n/a' : up ? 'up' : 'down';
        return `${state}${client ? ` (${client})` : ''}`;
    }

    function formatMarketplace(cached, url) {
        const state = cached === undefined ? 'unknown' : cached ? 'cached' : 'missing';
        return url ? `${state} - ${url}` : state;
    }

    function formatPrivateKey(value) {
        if (value === true) return 'present';
        if (value === false) return 'missing';
        return 'unknown';
    }
});
