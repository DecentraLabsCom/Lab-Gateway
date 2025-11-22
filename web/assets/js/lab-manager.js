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
});
