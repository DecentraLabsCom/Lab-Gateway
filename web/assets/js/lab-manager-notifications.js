(function (root) {
    'use strict';

    const COMMON_TIMEZONES = [
        'UTC',
        'Europe/Madrid', 'Europe/London', 'Europe/Berlin', 'Europe/Paris',
        'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
        'America/Mexico_City', 'America/Sao_Paulo', 'America/Bogota',
        'Africa/Johannesburg', 'Africa/Cairo',
        'Asia/Dubai', 'Asia/Kolkata', 'Asia/Shanghai', 'Asia/Tokyo',
        'Australia/Sydney',
    ];

    function createController({
        documentImpl = typeof document === 'undefined' ? root.document : document,
        fetchImpl,
        showToast = () => {},
        getAuthTokenHandler = () => root.AuthTokenHandler,
        notificationsAccessModule = root.LabManagerNotificationsAccess,
        notificationsConfigModule = root.LabManagerNotificationsConfig,
        commonTimezones = COMMON_TIMEZONES,
        browserTimezone = typeof Intl === 'undefined'
            ? 'UTC'
            : (Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'),
        logger = console,
    }) {
        if (!notificationsAccessModule) {
            throw new Error('LabManagerNotificationsAccess must load before the notifications controller');
        }
        if (!notificationsConfigModule) {
            throw new Error('LabManagerNotificationsConfig must load before the notifications controller');
        }

        const $ = (selector) => documentImpl?.querySelector?.(selector) || null;
        const fields = {
            enabled: $('#enabled'),
            driver: $('#driver'),
            from: $('#from'),
            fromName: $('#fromName'),
            defaultTo: $('#defaultTo'),
            timezone: $('#timezone'),
            smtpHost: $('#smtpHost'),
            smtpPort: $('#smtpPort'),
            smtpUser: $('#smtpUser'),
            smtpPass: $('#smtpPass'),
            smtpStartTls: $('#smtpStartTls'),
            graphTenant: $('#graphTenant'),
            graphClientId: $('#graphClientId'),
            graphClientSecret: $('#graphClientSecret'),
            graphFrom: $('#graphFrom'),
            smtpSection: $('#smtpSection'),
            graphSection: $('#graphSection'),
            driverSummary: $('#driverSummary'),
            smtpPasswordHint: $('#smtpPasswordHint'),
            graphClientSecretHint: $('#graphClientSecretHint'),
        };
        const modal = $('#configModal');
        const configureBtn = $('#configureBtn');
        const closeModalBtn = $('#closeModal');
        const cancelModalBtn = $('#cancelModal');
        const configStatusEl = $('#configStatus');
        const notificationsAccessGateEl = $('#notificationsAccessGate');
        const notificationsConfigContentEl = $('#notificationsConfigContent');
        const unlockNotificationsBtn = $('#unlockNotificationsBtn');
        const btnTestLoad = $('#btnTestLoad');
        const saveConfigBtn = $('#saveConfigBtn');
        const btnTestEmail = $('#btnTestEmail');

        const notificationsConfigController = notificationsConfigModule.createController({
            fields,
            commonTimezones,
            browserTimezone,
        });
        const applyNotificationConfig = notificationsConfigController.applyConfig;
        const buildNotificationPayload = notificationsConfigController.buildPayload;
        const populateTimezones = notificationsConfigController.populateTimezones;
        const toggleSections = notificationsConfigController.toggleSections;
        const updateDriverSummary = notificationsConfigController.updateDriverSummary;

        function setNotificationsLocked(locked) {
            if (notificationsAccessGateEl) notificationsAccessGateEl.hidden = !locked;
            if (notificationsConfigContentEl) notificationsConfigContentEl.hidden = locked;
            [configureBtn, btnTestLoad, saveConfigBtn, btnTestEmail]
                .filter(Boolean)
                .forEach(button => { button.disabled = locked; });
        }

        function setStatus(text) {
            if (configStatusEl) configStatusEl.textContent = text;
        }

        function updateBillingStatusAction() {
            if (!configStatusEl) return;
            const needsToken = !notificationsAccessController.hasBillingAccess();
            configStatusEl.classList.toggle('token-required-action', needsToken);
            configStatusEl.title = needsToken ? 'Click to enter the Gateway administrator token' : '';
            configStatusEl.setAttribute('aria-disabled', needsToken ? 'false' : 'true');
        }

        const notificationsAccessController = notificationsAccessModule.createController({
            fetchImpl,
            applyNotificationConfig,
            setNotificationsLocked,
            setStatus,
            updateBillingStatusAction,
            showToast,
            getAuthTokenHandler,
            logger,
        });
        const hasBillingAccess = notificationsAccessController.hasBillingAccess;
        const loadConfig = notificationsAccessController.loadConfig;
        const promptBillingToken = notificationsAccessController.promptBillingToken;
        const requestAccess = notificationsAccessController.requestAccess;
        const requireAccess = notificationsAccessController.requireAccess;

        function saveConfig() {
            if (!hasBillingAccess()) {
                requireAccess(() => saveConfig());
                return Promise.resolve(false);
            }

            const payload = buildNotificationPayload();
            return fetchImpl('/billing/admin/notifications', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload),
            })
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    applyNotificationConfig(data.config || {
                        ...payload,
                        smtp: {
                            ...payload.smtp,
                            passwordConfigured: Boolean(payload.smtp.password),
                        },
                        graph: {
                            ...payload.graph,
                            clientSecretConfigured: Boolean(payload.graph.clientSecret),
                        },
                    });
                    setStatus('Saved');
                    showToast('Configuration saved', 'success');
                    return true;
                })
                .catch(err => {
                    logger.error(err);
                    setStatus('Error');
                    showToast('Save failed (check admin access)', 'error');
                    return false;
                });
        }

        function sendTestEmail() {
            if (!hasBillingAccess()) {
                requireAccess(() => sendTestEmail());
                return Promise.resolve(false);
            }

            return fetchImpl('/billing/admin/notifications/test', {
                method: 'POST',
                credentials: 'include',
            })
                .then(async res => {
                    const body = await res.json().catch(() => ({}));
                    if (!res.ok || body.success === false) {
                        const msg = body.error || `Test failed (HTTP ${res.status})`;
                        throw new Error(msg);
                    }
                    showToast('Test email sent (check recipients)', 'success');
                    return true;
                })
                .catch(err => {
                    logger.error(err);
                    showToast(err.message || 'Test email failed', 'error');
                    return false;
                });
        }

        function openModal() {
            if (modal) modal.classList.add('show');
        }

        function closeModal() {
            if (modal) modal.classList.remove('show');
            updateDriverSummary();
        }

        function initialize() {
            if (fields.timezone) populateTimezones();

            if (btnTestLoad) {
                btnTestLoad.addEventListener('click', () => {
                    if (!hasBillingAccess()) {
                        requireAccess(() => loadConfig(), () => loadConfig());
                        return;
                    }
                    loadConfig();
                });
            }
            if (saveConfigBtn) saveConfigBtn.addEventListener('click', saveConfig);
            if (btnTestEmail) btnTestEmail.addEventListener('click', sendTestEmail);
            if (fields.driver) fields.driver.addEventListener('change', toggleSections);
            if (configureBtn) {
                configureBtn.addEventListener('click', () => {
                    if (!hasBillingAccess()) {
                        requireAccess(() => openModal(), () => loadConfig(() => {
                            openModal();
                        }));
                        return;
                    }
                    openModal();
                });
            }
            if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
            if (cancelModalBtn) cancelModalBtn.addEventListener('click', closeModal);

            if (configStatusEl) {
                configStatusEl.setAttribute('role', 'button');
                configStatusEl.tabIndex = 0;
                configStatusEl.addEventListener('click', () => {
                    if (!hasBillingAccess()) promptBillingToken(() => loadConfig());
                });
                configStatusEl.addEventListener('keydown', (event) => {
                    if ((event.key === 'Enter' || event.key === ' ') && !hasBillingAccess()) {
                        event.preventDefault();
                        promptBillingToken(() => loadConfig());
                    }
                });
            }

            updateBillingStatusAction();
            setNotificationsLocked(true);
            if (unlockNotificationsBtn) unlockNotificationsBtn.addEventListener('click', requestAccess);
        }

        return Object.freeze({
            closeModal,
            hasBillingAccess,
            initialize,
            loadConfig,
            openModal,
            promptBillingToken,
            requestAccess,
            requireAccess,
            saveConfig,
            sendTestEmail,
            setNotificationsLocked,
        });
    }

    root.LabManagerNotifications = Object.freeze({ createController });
})(window);
