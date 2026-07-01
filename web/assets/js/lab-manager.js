// Utility function to escape HTML and prevent XSS attacks
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    const BILLING_TOKEN_STORAGE_KEY = 'dlabs_billing_token';

    function isUsableToken(value) {
        if (typeof value !== 'string') return false;
        const token = value.trim();
        if (!token || token === '=') return false;
        const lower = token.toLowerCase();
        return lower !== 'change_me' && lower !== 'changeme';
    }

    function hasBillingToken() {
        try {
            return isUsableToken(localStorage.getItem(BILLING_TOKEN_STORAGE_KEY));
        } catch (_) {
            return false;
        }
    }

    let billingAccessReady = false;

    function hasBillingAccess() {
        return billingAccessReady || hasBillingToken();
    }

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

    const activityFeedState = {
        limit: 8,
        offset: 0,
        operations: [],
        pagination: null,
        loading: false
    };
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
    const configStatusEl = $('#configStatus');

    // Modal controls
    const modal = $('#configModal');
    const configureBtn = $('#configureBtn');
    const closeModalBtn = $('#closeModal');
    const cancelModalBtn = $('#cancelModal');
    const provisionHostModal = $('#provisionHostModal');
    const closeProvisionHostModalBtn = $('#closeProvisionHostModal');
    const cancelProvisionHostBtn = $('#cancelProvisionHost');
    const saveProvisionHostBtn = $('#saveProvisionHost');
    const winrmCredentialsModal = $('#winrmCredentialsModal');
    const closeWinrmCredentialsModalBtn = $('#closeWinrmCredentialsModal');
    const cancelWinrmCredentialsBtn = $('#cancelWinrmCredentials');
    const saveWinrmCredentialsBtn = $('#saveWinrmCredentials');
    const winrmCredentialRefEl = $('#winrmCredentialRef');
    const winrmCredentialAddressEl = $('#winrmCredentialAddress');
    const winrmCredentialUserEl = $('#winrmCredentialUser');
    const winrmCredentialPasswordEl = $('#winrmCredentialPassword');
    const provisionConnectionIdEl = $('#provisionConnectionId');
    const provisionHostNameEl = $('#provisionHostName');
    const provisionHostNameCandidatesEl = $('#provisionHostNameCandidates');
    const provisionHostAddressEl = $('#provisionHostAddress');
    const provisionHostMacEl = $('#provisionHostMac');
    const provisionHostLabsEl = $('#provisionHostLabs');
    const provisionHeartbeatPathEl = $('#provisionHeartbeatPath');

    populateTimezones();

    $('#btnTestLoad').addEventListener('click', loadConfig);
    $('#saveConfigBtn').addEventListener('click', saveConfig);
    $('#btnTestEmail').addEventListener('click', sendTestEmail);
    driverEl.addEventListener('change', toggleSections);
    configureBtn.addEventListener('click', () => {
        if (!hasBillingAccess()) {
            loadConfig(() => {
                openModal();
            });
            return;
        }
        openModal();
    });
    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);
    if (closeProvisionHostModalBtn) closeProvisionHostModalBtn.addEventListener('click', closeProvisionHostModal);
    if (cancelProvisionHostBtn) cancelProvisionHostBtn.addEventListener('click', closeProvisionHostModal);
    if (saveProvisionHostBtn) saveProvisionHostBtn.addEventListener('click', saveProvisionedHost);
    if (closeWinrmCredentialsModalBtn) closeWinrmCredentialsModalBtn.addEventListener('click', closeWinrmCredentialsModal);
    if (cancelWinrmCredentialsBtn) cancelWinrmCredentialsBtn.addEventListener('click', closeWinrmCredentialsModal);
    if (saveWinrmCredentialsBtn) saveWinrmCredentialsBtn.addEventListener('click', saveWinrmCredentials);

    loadConfig();
    loadAccessPolicy();
    checkOpsAvailability();
    updateBillingStatusAction();
    loadActivityFeed();

    // Lab Station ops state
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const guacamoleCandidateListEl = $('#guacamoleCandidateList');
    const hostState = {};
    const hostMetadata = {};
    const guacamoleCandidateState = {};
    const heartbeatSources = {};
    let hostNames = [];
    let guacamoleCandidates = [];

    // FMU AAS sync elements
    const fmuSyncBtn = $('#fmuSyncBtn');
    const fmuSyncKeyEl = $('#fmuSyncKey');
    const fmuSyncLabIdEl = $('#fmuSyncLabId');
    const fmuSyncFileEl = $('#fmuSyncFile');
    const fmuSyncResultEl = $('#fmuSyncResult');
    const fmuSyncDescriptionEl = $('#fmuSyncDescription');
    const fmuSyncLicenseEl = $('#fmuSyncLicense');
    const fmuSyncDocsUrlEl = $('#fmuSyncDocsUrl');
    const fmuSyncContactEmailEl = $('#fmuSyncContactEmail');
    const fmuSyncDescriptionHintEl = $('#fmuSyncDescriptionHint');
    const fmuSyncLicenseHintEl = $('#fmuSyncLicenseHint');

    // Track which fields were auto-filled from the FMU so we don't clobber
    // manual edits and can restore editability when the key changes.
    const fmuAutoFilled = { description: false, license: false };

    function _setFmuFieldFromHint(inputEl, hintEl, value) {
        if (!inputEl) return;
        inputEl.value = value;
        inputEl.readOnly = true;
        inputEl.style.opacity = '0.7';
        inputEl.style.cursor = 'default';
        if (hintEl) { hintEl.textContent = '\u2139\ufe0f From FMU'; hintEl.hidden = false; }
    }

    function _clearFmuFieldHint(inputEl, hintEl) {
        if (!inputEl) return;
        inputEl.readOnly = false;
        inputEl.style.opacity = '';
        inputEl.style.cursor = '';
        if (hintEl) { hintEl.textContent = ''; hintEl.hidden = true; }
    }

    function _clearAllFmuHints() {
        if (fmuAutoFilled.description) {
            _clearFmuFieldHint(fmuSyncDescriptionEl, fmuSyncDescriptionHintEl);
            if (fmuSyncDescriptionEl) fmuSyncDescriptionEl.value = '';
            fmuAutoFilled.description = false;
        }
        if (fmuAutoFilled.license) {
            _clearFmuFieldHint(fmuSyncLicenseEl, fmuSyncLicenseHintEl);
            if (fmuSyncLicenseEl) fmuSyncLicenseEl.value = '';
            fmuAutoFilled.license = false;
        }
    }

    async function _fetchFmuHints(accessKey) {
        if (!accessKey) { _clearAllFmuHints(); return; }
        try {
            const res = await fetch(`/aas-admin/fmu/${encodeURIComponent(accessKey)}/hints`);
            if (!res.ok) { _clearAllFmuHints(); return; }
            const hints = await res.json();
            // description
            if (hints.description && fmuSyncDescriptionEl && !fmuSyncDescriptionEl.value.trim()) {
                _setFmuFieldFromHint(fmuSyncDescriptionEl, fmuSyncDescriptionHintEl, hints.description);
                fmuAutoFilled.description = true;
            }
            // license
            if (hints.license && fmuSyncLicenseEl && !fmuSyncLicenseEl.value.trim()) {
                _setFmuFieldFromHint(fmuSyncLicenseEl, fmuSyncLicenseHintEl, hints.license);
                fmuAutoFilled.license = true;
            }
        } catch (_) {
            // hints are best-effort, ignore errors
        }
    }

    if (fmuSyncKeyEl) {
        fmuSyncKeyEl.addEventListener('blur', () => {
            const key = fmuSyncKeyEl.value.trim();
            if (!key) { _clearAllFmuHints(); return; }
            _fetchFmuHints(key);
        });
        fmuSyncKeyEl.addEventListener('input', () => {
            // User is editing the key — clear any previous auto-filled locks
            _clearAllFmuHints();
        });
    }

    if (fmuSyncBtn) {
        fmuSyncBtn.addEventListener('click', () => {
            const accessKey = (fmuSyncKeyEl && fmuSyncKeyEl.value || '').trim();
            const labId = (fmuSyncLabIdEl && fmuSyncLabIdEl.value || '').trim();
            const file = fmuSyncFileEl && fmuSyncFileEl.files && fmuSyncFileEl.files[0];
            const description = (fmuSyncDescriptionEl && fmuSyncDescriptionEl.value || '').trim();
            const license = (fmuSyncLicenseEl && fmuSyncLicenseEl.value || '').trim();
            const docsUrl = (fmuSyncDocsUrlEl && fmuSyncDocsUrlEl.value || '').trim();
            const contactEmail = (fmuSyncContactEmailEl && fmuSyncContactEmailEl.value || '').trim();
            syncAasFmu(accessKey, labId, file || null, { description, license, docsUrl, contactEmail });
        });
    }
    
    // AAS Link elements
    const aasLinkKeyEl = $('#aasLinkKey');
    const aasLinkLabIdEl = $('#aasLinkLabId');
    const aasLinkAasIdEl = $('#aasLinkAasId');
    const aasLinkSaveBtn = $('#aasLinkSaveBtn');
    const aasLinkCheckBtn = $('#aasLinkCheckBtn');
    const aasLinkDeleteBtn = $('#aasLinkDeleteBtn');
    const aasLinkResultEl = $('#aasLinkResult');

    function _aasLinkShowResult(msg, isError) {
        if (!aasLinkResultEl) return;
        aasLinkResultEl.textContent = msg;
        aasLinkResultEl.style.color = isError
            ? 'var(--color-error, #c0392b)'
            : 'var(--color-success, #1a7f4b)';
    }

    if (aasLinkSaveBtn) {
        aasLinkSaveBtn.addEventListener('click', async () => {
            const accessKey = (aasLinkKeyEl && aasLinkKeyEl.value || '').trim();
            const labId = (aasLinkLabIdEl && aasLinkLabIdEl.value || '').trim();
            const aasId = (aasLinkAasIdEl && aasLinkAasIdEl.value || '').trim();
            if (!accessKey) { showToast('Enter an access key', 'error'); return; }
            if (!aasId) { showToast('Enter an external AAS ID', 'error'); return; }
            aasLinkSaveBtn.disabled = true;
            try {
                const body = { aasId };
                if (labId) body.labId = labId;
                const res = await fetch(`/aas-admin/fmu/${encodeURIComponent(accessKey)}/aas-link`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    throw new Error(body.detail || `HTTP ${res.status}`);
                }
                const data = await res.json();
                _aasLinkShowResult(`Linked: ${data.aasId}`, false);
                showToast(`AAS link saved for ${accessKey}`, 'success');
            } catch (err) {
                _aasLinkShowResult(err.message, true);
                showToast(`AAS link failed: ${err.message}`, 'error');
            } finally {
                aasLinkSaveBtn.disabled = false;
            }
        });
    }

    if (aasLinkCheckBtn) {
        aasLinkCheckBtn.addEventListener('click', async () => {
            const accessKey = (aasLinkKeyEl && aasLinkKeyEl.value || '').trim();
            if (!accessKey) { showToast('Enter an access key', 'error'); return; }
            aasLinkCheckBtn.disabled = true;
            try {
                const res = await fetch(`/aas-admin/fmu/${encodeURIComponent(accessKey)}/aas-link`);
                if (res.status === 404) {
                    _aasLinkShowResult('No link configured for this access key.', false);
                    if (aasLinkAasIdEl) aasLinkAasIdEl.value = '';
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                _aasLinkShowResult(`Current link: ${data.aasId}`, false);
                if (aasLinkAasIdEl) aasLinkAasIdEl.value = data.aasId || '';
                if (aasLinkLabIdEl) aasLinkLabIdEl.value = data.labId || '';
            } catch (err) {
                _aasLinkShowResult(err.message, true);
            } finally {
                aasLinkCheckBtn.disabled = false;
            }
        });
    }

    if (aasLinkDeleteBtn) {
        aasLinkDeleteBtn.addEventListener('click', async () => {
            const accessKey = (aasLinkKeyEl && aasLinkKeyEl.value || '').trim();
            if (!accessKey) { showToast('Enter an access key', 'error'); return; }
            aasLinkDeleteBtn.disabled = true;
            try {
                const res = await fetch(`/aas-admin/fmu/${encodeURIComponent(accessKey)}/aas-link`, {
                    method: 'DELETE',
                });
                if (res.status === 404) {
                    _aasLinkShowResult('No link configured for this access key.', false);
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                _aasLinkShowResult('Link removed.', false);
                if (aasLinkAasIdEl) aasLinkAasIdEl.value = '';
                showToast(`AAS link removed for ${accessKey}`, 'success');
            } catch (err) {
                _aasLinkShowResult(err.message, true);
                showToast(`Remove link failed: ${err.message}`, 'error');
            } finally {
                aasLinkDeleteBtn.disabled = false;
            }
        });
    }

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

    if (refreshHostsBtn) {
        refreshHostsBtn.addEventListener('click', refreshAllHosts);
    }
    if (hostListEl) {
        hostListEl.addEventListener('click', handleHostActions);
        renderHosts();
        hostNames.forEach(startHeartbeatStream);
        loadHostInventory();
    }
    if (guacamoleCandidateListEl) {
        guacamoleCandidateListEl.addEventListener('click', handleGuacamoleCandidateActions);
    }

    function loadConfig(onSuccess) {
        setStatus('Loading...');
        updateBillingStatusAction();
        return fetch('/billing/admin/notifications', { credentials: 'include' })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                billingAccessReady = true;
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
                updateBillingStatusAction();
                showToast('Configuration loaded', 'success');
                if (typeof onSuccess === 'function') {
                    onSuccess();
                }
            })
            .catch(err => {
                console.error(err);
                billingAccessReady = false;
                const needsToken = err.message === 'HTTP 401';
                setStatus(needsToken ? 'Admin access token required' : 'Error');
                updateBillingStatusAction();
                showToast(needsToken ? 'Enter Wallet & Billing token to load notifications' : 'Cannot load config (check admin access)', 'error');
            });
    }

    function saveConfig() {
        if (!hasBillingAccess()) {
            promptBillingToken(() => saveConfig());
            return;
        }

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

        fetch('/billing/admin/notifications', {
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
        if (configStatusEl) {
            configStatusEl.textContent = text;
        }
    }

    function promptBillingToken(onSuccess) {
        const handler = window.AuthTokenHandler;
        if (!handler || typeof handler.showTokenModal !== 'function') {
            showToast('Token prompt unavailable on this page', 'error');
            return;
        }

        let config = null;
        if (typeof handler.getTokenConfigForPath === 'function') {
            config = handler.getTokenConfigForPath('/billing/admin/notifications');
        }
        if (!config) {
            config = {
                key: BILLING_TOKEN_STORAGE_KEY,
                header: 'X-Access-Token',
                cookie: 'access_token',
                title: 'Wallet & Billing Access Token',
                description: 'This area requires a Wallet & Billing access token.'
            };
        }

        handler.showTokenModal(config, () => {
            billingAccessReady = true;
            if (typeof onSuccess === 'function') {
                onSuccess();
            }
        });
    }

    function updateBillingStatusAction() {
        if (!configStatusEl) {
            return;
        }
        const needsToken = !hasBillingAccess();
        configStatusEl.classList.toggle('token-required-action', needsToken);
        configStatusEl.title = needsToken ? 'Click to enter Wallet & Billing token' : '';
        configStatusEl.setAttribute('aria-disabled', needsToken ? 'false' : 'true');
    }

    if (configStatusEl) {
        configStatusEl.setAttribute('role', 'button');
        configStatusEl.tabIndex = 0;
        configStatusEl.addEventListener('click', () => {
            if (!hasBillingAccess()) {
                promptBillingToken(() => loadConfig());
            }
        });
        configStatusEl.addEventListener('keydown', (e) => {
            if ((e.key === 'Enter' || e.key === ' ') && !hasBillingAccess()) {
                e.preventDefault();
                promptBillingToken(() => loadConfig());
            }
        });
    }

    function sendTestEmail() {
        if (!hasBillingAccess()) {
            promptBillingToken(() => sendTestEmail());
            return;
        }

        fetch('/billing/admin/notifications/test', {
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

    async function loadAccessPolicy() {
        const badge = $('#labManagerAccessBadge');
        if (!badge) return;
        try {
            const res = await fetch('/lab-manager/access-policy', {
                credentials: 'include',
                skipAuthPrompt: true
            });
            if (res.status === 401) {
                badge.textContent = 'Access Policy Requires Token';
                badge.classList.remove('local', 'private', 'external');
                return;
            }
            if (res.status === 403) {
                badge.textContent = 'Access Policy Blocked';
                badge.classList.remove('local', 'private', 'external');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const status = await res.json();
            updateAccessPolicyBadge(status);
        } catch (err) {
            badge.textContent = 'Access Policy Unavailable';
            badge.classList.remove('local', 'private', 'external');
        }
    }

    function updateAccessPolicyBadge(status) {
        const badge = $('#labManagerAccessBadge');
        if (!badge || !status) return;

        const localOnly = status.dashboardLocalOnly !== false;
        const privateEnabled = status.allowPrivateNetworks === true && status.dashboardAllowPrivate === true;
        const cidrs = typeof status.dashboardAllowedCidrs === 'string'
            ? status.dashboardAllowedCidrs.split(',').map(item => item.trim()).filter(Boolean)
            : [];

        badge.classList.remove('local', 'private', 'external');
        if (!localOnly) {
            badge.textContent = 'External Access Allowed';
            badge.classList.add('external');
        } else if (privateEnabled && cidrs.length > 0) {
            badge.textContent = 'Private CIDR Allowlist';
            badge.title = cidrs.join(', ');
            badge.classList.add('private');
        } else if (privateEnabled) {
            badge.textContent = 'Any Private Network';
            badge.classList.add('private');
        } else {
            badge.textContent = 'Localhost Only';
            badge.classList.add('local');
        }
    }

    // ---- Lab Station ops helpers ----
    async function loadHostInventory() {
        try {
            const res = await fetch('/ops/api/hosts');
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const hosts = Array.isArray(data.hosts) ? data.hosts : [];
            Object.keys(hostMetadata).forEach(key => delete hostMetadata[key]);
            hosts.forEach(host => {
                if (host && host.name) {
                    hostMetadata[host.name] = host;
                }
            });

            const nextHostNames = hosts.map(host => host.name).filter(Boolean);
            const nextSet = new Set(nextHostNames);
            hostNames
                .filter(name => !nextSet.has(name))
                .forEach(stopHeartbeatStream);
            hostNames = nextHostNames;
            renderHosts();
            guacamoleCandidates = data.guacamoleUnmatched || [];
            guacamoleCandidates.forEach(rememberGuacamoleCandidate);
            renderGuacamoleCandidates(guacamoleCandidates);
            hostNames.forEach(startHeartbeatStream);
            updateOpsHint(data);
        } catch (err) {
            console.warn('Unable to load ops host inventory', err);
            updateOpsHint(null);
        }
    }

    function updateOpsHint(data) {
        const opsHint = $('#opsHint');
        if (!opsHint) return;
        if (!data) {
            opsHint.textContent = 'The ops inventory could not be loaded.';
            return;
        }
        const unmatchedCount = Array.isArray(data.guacamoleUnmatched) ? data.guacamoleUnmatched.length : 0;
        const guacStatus = data.guacamoleAvailable
            ? `${unmatchedCount} Guacamole connection${unmatchedCount === 1 ? '' : 's'} not linked to an ops host.`
            : 'Guacamole inventory unavailable.';
        opsHint.textContent = `Hosts are loaded from ops-worker/hosts.json and ops-data/hosts.json. ${guacStatus}`;
    }

    function startHeartbeatStream(host) {
        if (!host || !window.EventSource || heartbeatSources[host]) return;
        const url = new URL('/ops/api/heartbeat/stream', window.location.origin);
        url.searchParams.set('host', host);
        url.searchParams.set('include_events', 'false');

        const source = new EventSource(url.toString());
        heartbeatSources[host] = source;

        source.addEventListener('heartbeat', evt => {
            try {
                const data = JSON.parse(evt.data || '{}');
                hostState[host] = data;
                renderHosts();
                loadActivityFeed();
            } catch (err) {
                console.warn('Heartbeat SSE parse failed', err);
            }
        });

        source.addEventListener('error', evt => {
            const errorText = evt?.data || 'Heartbeat SSE connection error';
            if (source.readyState === EventSource.CLOSED) {
                stopHeartbeatStream(host);
            }
            showToast(`Heartbeat stream error for ${host}: ${errorText}`, 'error');
        });
    }

    function stopHeartbeatStream(host) {
        const source = heartbeatSources[host];
        if (!source) return;
        try {
            source.close();
        } catch (_) {
            // ignore
        }
        delete heartbeatSources[host];
    }

    function renderHosts() {
        if (!hostListEl) return;
        hostListEl.innerHTML = '';
        if (!hostNames.length) {
            hostListEl.innerHTML = '<div class="empty">No ops hosts loaded. Configure ops-worker/hosts.json.</div>';
            return;
        }
        hostNames.forEach(host => {
            hostListEl.appendChild(buildHostRow(host));
        });
    }

    function buildHostRow(host) {
        const data = hostState[host] || {};
        const meta = hostMetadata[host] || {};
        const guacamole = meta.guacamole || {};
        const heartbeat = data.heartbeat || {};
        const summary = heartbeat.summary || {};
        const status = heartbeat.status || {};
        const operations = heartbeat.operations || {};
        const winrmConfigured = Boolean(meta.winrmConfigured);
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
        const safeGuacamole = escapeHtml(formatGuacamoleStatus(guacamole));
        const guacamoleClass = guacamoleStatusClass(guacamole.status);

        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.host = host;
        row.innerHTML = `
            <div>
                <div class="host-title">${safeHost}</div>
                <div class="host-meta">Updated: ${safeUpdated}</div>
                <div class="host-meta">Guacamole: <span class="pill ${guacamoleClass}">${safeGuacamole}</span></div>
                <div class="host-meta">WinRM credentials: <span class="pill ${winrmConfigured ? 'good' : 'warn'}">${winrmConfigured ? 'configured' : 'missing'}</span></div>
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
                <button class="mini-btn secondary" data-action="toggle-local-mode">${localMode ? 'Disable' : 'Enable'} Local</button>
                <button class="mini-btn" data-action="set-winrm-credentials">WinRM Credentials</button>
                <button class="mini-btn" data-action="sync-aas" title="Sync Digital Twin metadata to BaSyx AAS server">Sync AAS</button>
            </div>
        `;
        return row;
    }

    function renderGuacamoleCandidates(candidates) {
        if (!guacamoleCandidateListEl) return;
        guacamoleCandidateListEl.innerHTML = '';
        if (!Array.isArray(candidates) || !candidates.length) {
            guacamoleCandidateListEl.innerHTML = '<div class="empty">All Guacamole connections are linked or no connections are configured.</div>';
            return;
        }
        candidates.forEach(candidate => {
            guacamoleCandidateListEl.appendChild(buildGuacamoleCandidateRow(candidate));
        });
    }

    function buildGuacamoleCandidateRow(candidate) {
        const id = String(candidate.id ?? '');
        const state = guacamoleCandidateState[id] || {};
        const safeName = escapeHtml(candidate.name || 'Unnamed connection');
        const safeHost = escapeHtml(candidate.hostname || 'n/a');
        const safeProtocol = escapeHtml(candidate.protocol || 'unknown');
        const safePort = escapeHtml(candidate.port || 'n/a');
        const statusText = formatDiscoveryStatus(state.status);
        const statusClass = discoveryStatusClass(state.status);
        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.connectionId = id;
        row.innerHTML = `
            <div>
                <div class="host-title">${safeName}</div>
                <div class="host-meta">Host: ${safeHost}</div>
                <div class="host-meta">Protocol: ${safeProtocol} · Port: ${safePort}</div>
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

    async function handleGuacamoleCandidateActions(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const row = btn.closest('.host-row');
        const connectionId = row?.dataset.connectionId;
        if (!connectionId) return;
        if (btn.dataset.action === 'configure-candidate') {
            openProvisionHostModal(connectionId);
            return;
        }
        if (btn.dataset.action !== 'probe-candidate') return;
        const candidate = findGuacamoleCandidate(connectionId);
        guacamoleCandidateState[connectionId] = {
            ...(guacamoleCandidateState[connectionId] || {}),
            candidate,
            status: 'checking'
        };
        btn.disabled = true;
        renderGuacamoleCandidates(guacamoleCandidates);
        try {
            const res = await fetch('/ops/api/hosts/discover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ connectionId })
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body.error || `HTTP ${res.status}`);
            }
            const winrmOpen = Object.entries(body.checks?.winrm || {})
                .filter(([, open]) => open)
                .map(([port]) => port);
            const suggestedMac = body.opsHostDraft?.mac;
            const detail = body.status === 'labstation-detected'
                ? `HTTP health matched at ${body.checks?.labStationHttp?.url || 'configured discovery endpoint'}`
                : winrmOpen.length
                    ? `Open WinRM port${winrmOpen.length === 1 ? '' : 's'}: ${winrmOpen.join(', ')}`
                    : 'No Lab Station health endpoint or WinRM port detected.';
            guacamoleCandidateState[connectionId] = {
                ...(guacamoleCandidateState[connectionId] || {}),
                candidate: body.connection || candidate,
                status: body.status,
                detail: suggestedMac ? `${detail} Suggested MAC: ${suggestedMac}` : detail,
                opsHostDraft: body.opsHostDraft || {}
            };
            showToast(`Discovery finished for ${body.connection?.hostname || connectionId}`, 'success');
        } catch (err) {
            console.error(err);
            guacamoleCandidateState[connectionId] = {
                ...(guacamoleCandidateState[connectionId] || {}),
                candidate,
                status: 'error',
                detail: err.message
            };
            showToast(`Lab Station check failed: ${err.message}`, 'error');
        } finally {
            loadHostInventory();
        }
    }

    function findGuacamoleCandidate(connectionId) {
        const key = String(connectionId);
        return guacamoleCandidates.find(candidate => String(candidate.id ?? '') === key)
            || guacamoleCandidateState[key]?.candidate
            || null;
    }

    function rememberGuacamoleCandidate(candidate) {
        const id = String(candidate?.id ?? '');
        if (!id) return;
        guacamoleCandidateState[id] = {
            ...(guacamoleCandidateState[id] || {}),
            candidate
        };
    }

    function normalizeMatchValue(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function normalizeLooseValue(value) {
        return normalizeMatchValue(value).replace(/[^a-z0-9]+/g, '');
    }

    function urlHost(value) {
        const raw = (value || '').toString().trim();
        if (!raw) return '';
        try {
            return new URL(raw, window.location.origin).hostname.toLowerCase();
        } catch (_) {
            return '';
        }
    }

    function labMatchesConnection(lab, connection) {
        const connectionTokens = [
            connection.id,
            connection.name,
            connection.hostname
        ].map(normalizeMatchValue).filter(Boolean);
        const looseConnectionTokens = connectionTokens.map(normalizeLooseValue).filter(Boolean);
        const labTokens = [
            lab.accessKey,
            lab.accessURI,
            urlHost(lab.accessURI)
        ].map(normalizeMatchValue).filter(Boolean);
        const looseLabTokens = labTokens.map(normalizeLooseValue).filter(Boolean);

        if (labTokens.some(token => connectionTokens.includes(token))) return true;
        if (looseLabTokens.some(token => looseConnectionTokens.includes(token))) return true;
        if (connection.hostname && urlHost(lab.accessURI) === normalizeMatchValue(connection.hostname)) return true;
        return false;
    }

    async function loadLabCandidates() {
        const res = await fetch('/lab-admin/labs');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json().catch(() => ({}));
        return Array.isArray(body.labs) ? body.labs : [];
    }

    function renderProvisionLabOptions(labs, selectedIds = []) {
        if (!provisionHostLabsEl) return;
        provisionHostLabsEl.innerHTML = '';
        const selectedSet = new Set(selectedIds.map(String));
        if (!labs.length) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No matching labs found';
            option.disabled = true;
            provisionHostLabsEl.appendChild(option);
            provisionHostLabsEl.disabled = true;
            return;
        }
        provisionHostLabsEl.disabled = false;
        labs.forEach(lab => {
            const labId = String(lab.labId || '').trim();
            if (!labId) return;
            const option = document.createElement('option');
            option.value = labId;
            option.textContent = `Lab ${labId}${lab.accessKey ? ` - ${lab.accessKey}` : ''}`;
            option.selected = selectedSet.has(labId) || (labs.length === 1 && selectedSet.size === 0);
            provisionHostLabsEl.appendChild(option);
        });
    }

    function selectedProvisionLabIds() {
        if (!provisionHostLabsEl) return [];
        return Array.from(provisionHostLabsEl.selectedOptions || [])
            .map(option => option.value.trim())
            .filter(Boolean);
    }

    function provisionLabCandidateIds() {
        if (!provisionHostLabsEl) return [];
        return Array.from(provisionHostLabsEl.options || [])
            .map(option => option.value.trim())
            .filter(Boolean);
    }

    function renderProvisionNameCandidates(candidates) {
        if (!provisionHostNameCandidatesEl) return;
        provisionHostNameCandidatesEl.innerHTML = '';
        const seen = new Set();
        (Array.isArray(candidates) ? candidates : []).forEach(candidate => {
            const value = (candidate || '').toString().trim();
            if (!value || seen.has(value)) return;
            seen.add(value);
            const option = document.createElement('option');
            option.value = value;
            provisionHostNameCandidatesEl.appendChild(option);
        });
    }

    async function populateProvisionLabCandidates(connectionId, candidate, draft) {
        renderProvisionLabOptions([], []);
        provisionHostLabsEl.disabled = true;
        const loading = document.createElement('option');
        loading.value = '';
        loading.textContent = 'Loading lab candidates...';
        loading.disabled = true;
        provisionHostLabsEl.innerHTML = '';
        provisionHostLabsEl.appendChild(loading);
        try {
            const labs = await loadLabCandidates();
            const candidateLabs = labs.filter(lab => labMatchesConnection(lab, candidate));
            renderProvisionLabOptions(candidateLabs, draft.labs || []);
        } catch (err) {
            console.warn('Unable to load lab candidates', err);
            provisionHostLabsEl.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Unable to load lab candidates';
            option.disabled = true;
            provisionHostLabsEl.appendChild(option);
            provisionHostLabsEl.disabled = true;
        }
    }

    function openProvisionHostModal(connectionId) {
        const candidate = findGuacamoleCandidate(connectionId);
        if (
            !candidate ||
            !provisionHostModal ||
            !provisionConnectionIdEl ||
            !provisionHostNameEl ||
            !provisionHostAddressEl ||
            !provisionHostMacEl ||
            !provisionHostLabsEl ||
            !provisionHeartbeatPathEl
        ) {
            showToast('Host provisioning modal is unavailable', 'error');
            return;
        }
        const host = candidate.hostname || candidate.name || '';
        const draft = guacamoleCandidateState[String(connectionId)]?.opsHostDraft || {};
        provisionConnectionIdEl.value = String(connectionId);
        provisionHostNameEl.value = draft.name || host;
        renderProvisionNameCandidates(draft.nameCandidates || [candidate.name, candidate.hostname].filter(Boolean));
        provisionHostAddressEl.value = draft.address || candidate.hostname || '';
        provisionHostMacEl.value = draft.mac || '';
        populateProvisionLabCandidates(connectionId, candidate, draft);
        provisionHeartbeatPathEl.value = draft.heartbeat_path || 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json';
        provisionHostModal.classList.add('show');
    }

    function closeProvisionHostModal() {
        if (provisionHostModal) {
            provisionHostModal.classList.remove('show');
        }
    }

    function openWinrmCredentialsModal(host) {
        const meta = hostMetadata[host] || {};
        const credentialRef = meta.credentialRef || meta.address || host;
        if (
            !winrmCredentialsModal ||
            !winrmCredentialRefEl ||
            !winrmCredentialAddressEl ||
            !winrmCredentialUserEl ||
            !winrmCredentialPasswordEl
        ) {
            showToast('WinRM credentials modal is unavailable', 'error');
            return;
        }
        winrmCredentialRefEl.value = credentialRef;
        winrmCredentialAddressEl.value = meta.address || credentialRef;
        winrmCredentialUserEl.value = '.\\LabGatewaySvc';
        winrmCredentialPasswordEl.value = '';
        winrmCredentialsModal.classList.add('show');
    }

    function closeWinrmCredentialsModal() {
        if (winrmCredentialsModal) {
            winrmCredentialsModal.classList.remove('show');
        }
    }

    async function saveWinrmCredentials() {
        if (!winrmCredentialRefEl || !winrmCredentialUserEl || !winrmCredentialPasswordEl) {
            showToast('WinRM credentials modal is unavailable', 'error');
            return;
        }
        const payload = {
            credentialRef: winrmCredentialRefEl.value.trim(),
            user: winrmCredentialUserEl.value.trim(),
            password: winrmCredentialPasswordEl.value
        };
        if (!payload.credentialRef || !payload.user || !payload.password) {
            showToast('WinRM credential reference, user, and password are required', 'error');
            return;
        }
        if (saveWinrmCredentialsBtn) saveWinrmCredentialsBtn.disabled = true;
        try {
            const res = await fetch('/ops/api/hosts/winrm-credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body.error || `HTTP ${res.status}`);
            }
            closeWinrmCredentialsModal();
            showToast('WinRM credentials saved', 'success');
            loadHostInventory();
        } catch (err) {
            showToast(`WinRM credential save failed: ${err.message}`, 'error');
        } finally {
            if (saveWinrmCredentialsBtn) saveWinrmCredentialsBtn.disabled = false;
        }
    }

    async function saveProvisionedHost() {
        if (
            !provisionConnectionIdEl ||
            !provisionHostNameEl ||
            !provisionHostAddressEl ||
            !provisionHostMacEl ||
            !provisionHostLabsEl ||
            !provisionHeartbeatPathEl
        ) {
            showToast('Host provisioning modal is unavailable', 'error');
            return;
        }
        const payload = {
            connectionId: provisionConnectionIdEl.value,
            name: provisionHostNameEl.value.trim(),
            address: provisionHostAddressEl.value.trim(),
            mac: provisionHostMacEl.value.trim(),
            labs: selectedProvisionLabIds(),
            validLabIds: provisionLabCandidateIds(),
            credentialRef: provisionHostAddressEl.value.trim(),
            heartbeatPath: provisionHeartbeatPathEl.value.trim()
        };
        if (!payload.connectionId || !payload.name || !payload.address) {
            showToast('Name and address are required', 'error');
            return;
        }
        if (!payload.labs.length) {
            showToast('Select at least one matching lab', 'error');
            return;
        }
        if (saveProvisionHostBtn) saveProvisionHostBtn.disabled = true;
        try {
            const res = await fetch('/ops/api/hosts/provision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body.error || `HTTP ${res.status}`);
            }
            closeProvisionHostModal();
            showToast(`Ops host ${body.host?.name || payload.name} configured`, 'success');
            loadHostInventory();
        } catch (err) {
            console.error(err);
            showToast(`Configure host failed: ${err.message}`, 'error');
        } finally {
            if (saveProvisionHostBtn) saveProvisionHostBtn.disabled = false;
        }
    }

    function formatGuacamoleStatus(guacamole) {
        const connections = Array.isArray(guacamole.connections) ? guacamole.connections : [];
        if (guacamole.status === 'linked' && connections[0]) {
            const conn = connections[0];
            return `linked - ${conn.name || conn.hostname || 'connection'} (${conn.protocol || 'unknown'})`;
        }
        if (guacamole.status === 'ambiguous') {
            return `ambiguous - ${connections.length} matches`;
        }
        if (guacamole.status === 'missing') {
            return 'missing';
        }
        return 'unknown';
    }

    function guacamoleStatusClass(status) {
        if (status === 'linked') return 'good';
        if (status === 'ambiguous') return 'warn';
        if (status === 'missing') return 'bad';
        return 'soft';
    }

    function handleHostActions(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const host = btn.closest('.host-row')?.dataset.host;
        if (!host) return;
        const action = btn.dataset.action;
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
            return;
        }
        if (action === 'toggle-local-mode') {
            const currentMode = hostState[host]?.heartbeat?.status?.localModeEnabled;
            toggleLocalMode(host, !currentMode);
            return;
        }
        if (action === 'set-winrm-credentials') {
            openWinrmCredentialsModal(host);
            return;
        }
        if (action === 'sync-aas') {
            syncAasHost(host);
        }
    }

    function refreshAllHosts() {
        loadHostInventory();
        if (window.EventSource) {
            hostNames.forEach(startHeartbeatStream);
            showToast('Heartbeat streaming started for all hosts', 'success');
            return;
        }
        hostNames.forEach(pollHeartbeat);
    }

    async function pollHeartbeat(host) {
        try {
            const res = await fetch('/ops/api/heartbeat/poll', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host })
            });
            if (res.status === 403) {
                showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            hostState[host] = data;
            renderHosts();
            loadActivityFeed();
            showToast(`Heartbeat ${host} ok`, 'success');
        } catch (err) {
            console.error(err);
            showToast(`Heartbeat failed for ${host}: ${err.message}`, 'error');
        }
    }

    async function toggleLocalMode(host, enabled) {
        try {
            const res = await fetch('/ops/api/hosts/local-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, enabled })
            });
            if (res.status === 403) {
                showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            await pollHeartbeat(host);
            showToast(`Local mode ${data.localModeEnabled ? 'enabled' : 'disabled'} for ${host}`, 'success');
        } catch (err) {
            console.error(err);
            showToast(`Local mode toggle failed for ${host}: ${err.message}`, 'error');
        }
    }

    async function loadActivityFeed(append = false) {
        const activityFeed = $('#activityFeedList');
        if (!activityFeed) return;
        if (!append) {
            activityFeedState.offset = 0;
            activityFeedState.operations = [];
            activityFeedState.pagination = null;
        }
        activityFeedState.loading = true;
        activityFeed.innerHTML = '<div class="empty">Loading recent operations...</div>';
        try {
            const params = new URLSearchParams({
                limit: String(activityFeedState.limit),
                offset: String(activityFeedState.offset)
            });
            const res = await fetch(`/ops/api/operations/recent?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const body = await res.json();
            const entries = Array.isArray(body.operations) ? body.operations : [];
            activityFeedState.operations = append
                ? activityFeedState.operations.concat(entries)
                : entries;
            activityFeedState.pagination = normalizePagination(
                body.pagination,
                activityFeedState.offset,
                entries.length,
                activityFeedState.limit
            );
            activityFeedState.offset = activityFeedState.pagination.nextOffset;
            renderActivityFeed();
        } catch (err) {
            console.error(err);
            activityFeed.innerHTML = `<div class="empty">Unable to load activity: ${escapeHtml(err.message)}</div>`;
        } finally {
            activityFeedState.loading = false;
        }
    }

    function renderActivityFeed() {
        const activityFeed = $('#activityFeedList');
        if (!activityFeed) return;
        if (!activityFeedState.operations.length) {
            activityFeed.innerHTML = '<div class="empty">No recent activity available yet.</div>';
            return;
        }
        activityFeed.innerHTML = '';
        activityFeedState.operations.forEach(entry => {
            activityFeed.appendChild(renderActivityFeedItem(entry));
        });
        const paginationEl = renderActivityFeedPagination(activityFeedState.pagination);
        if (paginationEl) {
            activityFeed.appendChild(paginationEl);
        }
    }

    function renderActivityFeedPagination(pagination) {
        if (!pagination) return null;
        const footer = document.createElement('div');
        footer.className = 'activity-pagination';
        const summary = document.createElement('div');
        summary.className = 'activity-meta';
        const start = pagination.returned ? pagination.offset + 1 : pagination.offset;
        const end = pagination.offset + pagination.returned;
        summary.textContent = pagination.total
            ? `Showing ${start}-${end} of ${pagination.total}`
            : `Showing ${pagination.returned} entr${pagination.returned === 1 ? 'y' : 'ies'}`;
        footer.appendChild(summary);
        if (pagination.hasMore) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'mini-btn primary';
            btn.textContent = 'Load more';
            btn.disabled = activityFeedState.loading;
            btn.addEventListener('click', () => {
                if (!activityFeedState.loading) {
                    loadActivityFeed(true);
                }
            });
            footer.appendChild(btn);
        }
        return footer;
    }

    function renderActivityFeedItem(item) {
        const payloadText = item.payload && typeof item.payload === 'object'
            ? JSON.stringify(item.payload)
            : String(item.payload || '');
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `
            <div class="item-title">${escapeHtml(item.action)} (${escapeHtml(item.status)})</div>
            <div class="item-meta">${escapeHtml(item.host || 'unknown host')} · ${escapeHtml(formatDateTime(item.createdAt) || 'n/a')}</div>
            <div class="item-description">${escapeHtml(item.message || payloadText)}</div>
        `;
        return row;
    }

    function formatDateTime(value) {
        if (!value) return null;
        try {
            const dt = new Date(value);
            return dt.toLocaleString();
        } catch (_e) {
            return value;
        }
    }

    async function triggerWol(host) {
        try {
            const res = await fetch('/ops/api/wol', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host })
            });
            if (res.status === 403) {
                showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            showToast(`WoL ${host}: ${data.success ? 'sent' : 'failed'}`, data.success ? 'success' : 'error');
        } catch (err) {
            console.error(err);
            showToast(`WoL failed for ${host}: ${err.message}`, 'error');
        }
    }

    async function triggerWinrm(host, command, args = []) {
        try {
            const res = await fetch('/ops/api/winrm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, command, args })
            });
            if (res.status === 403) {
                showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const ok = data.exit_code === 0;
            showToast(`${command} on ${host}: ${ok ? 'ok' : 'err'}`, ok ? 'success' : 'error');
        } catch (err) {
            console.error(err);
            showToast(`${command} failed on ${host}: ${err.message}`, 'error');
        }
    }

    async function syncAasFmu(accessKey, labId, aasxFile, extraInfo = {}) {
        if (!accessKey) {
            showToast('Enter a FMU access key', 'error');
            return;
        }
        if (fmuSyncBtn) fmuSyncBtn.disabled = true;
        if (fmuSyncResultEl) fmuSyncResultEl.textContent = '';
        try {
            let res;
            const url = `/aas-admin/fmu/${encodeURIComponent(accessKey)}/sync`;
            if (aasxFile) {
                const form = new FormData();
                form.append('file', aasxFile);
                if (labId) form.append('labId', labId);
                if (extraInfo.description) form.append('description', extraInfo.description);
                if (extraInfo.license) form.append('license', extraInfo.license);
                if (extraInfo.docsUrl) form.append('documentationUrl', extraInfo.docsUrl);
                if (extraInfo.contactEmail) form.append('contactEmail', extraInfo.contactEmail);
                res = await fetch(url, { method: 'POST', body: form });
            } else {
                const params = new URLSearchParams();
                if (labId) params.set('labId', labId);
                if (extraInfo.description) params.set('description', extraInfo.description);
                if (extraInfo.license) params.set('license', extraInfo.license);
                if (extraInfo.docsUrl) params.set('documentationUrl', extraInfo.docsUrl);
                if (extraInfo.contactEmail) params.set('contactEmail', extraInfo.contactEmail);
                const qs = params.toString() ? `?${params.toString()}` : '';
                res = await fetch(url + qs, { method: 'POST' });
            }
            if (res.status === 403) {
                showToast('AAS admin unavailable in Lite mode or blocked by gateway policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || `HTTP ${res.status}`);
            }
            const data = await res.json();
            if (fmuSyncResultEl) {
                const msg = data.aasxUpload
                    ? `Synced ${(data.uploadedAasIds || []).length} shell(s) + ${(data.uploadedSubmodelIds || []).length} submodel(s) from AASX`
                    : `AAS shell synced — ${data.created ? 'created' : 'updated'}`;
                fmuSyncResultEl.textContent = msg;
                fmuSyncResultEl.style.color = 'var(--color-success, #1a7f4b)';
            }
            showToast(`FMU AAS sync: ${accessKey} ok`, 'success');
        } catch (err) {
            console.error(err);
            if (fmuSyncResultEl) {
                fmuSyncResultEl.textContent = err.message;
                fmuSyncResultEl.style.color = 'var(--color-error, #c0392b)';
            }
            showToast(`FMU AAS sync failed: ${err.message}`, 'error');
        } finally {
            if (fmuSyncBtn) fmuSyncBtn.disabled = false;
        }
    }

    async function syncAasHost(host) {
        try {
            const res = await fetch('/ops/api/aas-sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host })
            });
            if (res.status === 403) {
                showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                return;
            }
            if (res.status === 401) {
                showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const labs = data.labs || [];
            if (!labs.length) {
                showToast(`AAS sync ${host}: no labs mapped`, 'error');
                return;
            }
            const disabled = labs.every(l => l.disabled);
            if (disabled) {
                showToast(`AAS sync ${host}: AAS not configured on this gateway`, 'error');
                return;
            }
            const errors = labs.filter(l => l.error);
            if (errors.length) {
                showToast(`AAS sync ${host}: ${errors.length}/${labs.length} failed`, 'error');
            } else {
                showToast(`AAS sync ${host}: ${labs.length} lab(s) synced`, 'success');
            }
        } catch (err) {
            console.error(err);
            showToast(`AAS sync failed for ${host}: ${err.message}`, 'error');
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
            if (res.status === 403) {
                const msg = 'Access denied: /ops blocked by Lab Manager access policy';
                if (!append) setTimelineMessage(msg);
                showToast(msg, 'error');
                return;
            }
            if (res.status === 401) {
                const msg = 'Unauthorized: check LAB_MANAGER_TOKEN';
                if (!append) setTimelineMessage(msg);
                showToast(msg, 'error');
                return;
            }
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

    async function checkOpsAvailability() {
        try {
            const res = await fetch('/ops/health', { method: 'HEAD' });
            if (res.status === 403) {
                showOpsWarning();
                return false;
            }
            return res.ok || res.status === 401; // 401 = token issue, not network
        } catch {
            return false;
        }
    }

    function showOpsWarning() {
        const opsHint = $('#opsHint');
        if (opsHint) {
            opsHint.innerHTML = `
                <i class="fas fa-exclamation-triangle" style="color: #856404; margin-right: 8px;"></i>
                <strong>Access policy:</strong> Lab Station operations require an allowed Lab Manager network scope and a valid Lab Manager token.
                Check ADMIN_DASHBOARD_LOCAL_ONLY, ADMIN_DASHBOARD_ALLOW_PRIVATE, SECURITY_ALLOW_PRIVATE_NETWORKS, and ADMIN_ALLOWED_CIDRS.
            `;
            opsHint.style.backgroundColor = '#fff3cd';
            opsHint.style.color = '#856404';
            opsHint.style.padding = '12px';
            opsHint.style.borderRadius = '4px';
            opsHint.style.border = '1px solid #ffc107';
        }
        if (refreshHostsBtn) refreshHostsBtn.disabled = true;
        if (timelineBtn) timelineBtn.disabled = true;
    }});
