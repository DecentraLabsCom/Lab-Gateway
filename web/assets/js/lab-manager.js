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

    // Modal controls
    const modal = $('#configModal');
    const configureBtn = $('#configureBtn');
    const closeModalBtn = $('#closeModal');
    const cancelModalBtn = $('#cancelModal');

    populateTimezones();

    $('#btnTestLoad').addEventListener('click', loadConfig);
    $('#saveConfigBtn').addEventListener('click', saveConfig);
    $('#btnTestEmail').addEventListener('click', () => showToast('Test email not implemented yet', 'error'));
    driverEl.addEventListener('change', toggleSections);
    configureBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);

    loadConfig();

    // Lab Station ops state
    const hostInput = $('#hostInput');
    const addHostBtn = $('#addHostBtn');
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const hostState = {};
    let hostNames = loadHosts();

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

        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.host = host;
        row.innerHTML = `
            <div>
                <div class="host-title">${host}</div>
                <div class="host-meta">Updated: ${updated || 'n/a'}</div>
                <div class="host-meta">Last forced logoff: ${(lastForced && lastForced.timestamp) || 'n/a'}</div>
                <div class="host-meta">Last power: ${(lastPower && lastPower.mode) ? `${lastPower.mode} @ ${lastPower.timestamp}` : 'n/a'}</div>
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
});
