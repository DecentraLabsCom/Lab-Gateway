// Utility function to escape HTML and prevent XSS attacks
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    let billingAccessReady = false;
    let billingAccessPromise = null;
    let billingTokenRequired = false;

    function hasBillingAccess() {
        return billingAccessReady;
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
    const notificationsAccessGateEl = $('#notificationsAccessGate');
    const notificationsConfigContentEl = $('#notificationsConfigContent');
    const unlockNotificationsBtn = $('#unlockNotificationsBtn');
    const smtpPasswordHintEl = $('#smtpPasswordHint');
    const graphClientSecretHintEl = $('#graphClientSecretHint');

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
    const provisionHostLabsSummaryEl = $('#provisionHostLabsSummary');
    const provisionHeartbeatPathEl = $('#provisionHeartbeatPath');

    populateTimezones();

    $('#btnTestLoad').addEventListener('click', () => {
        if (!hasBillingAccess()) {
            requireBillingAccess(() => loadConfig(), () => loadConfig());
            return;
        }
        loadConfig();
    });
    $('#saveConfigBtn').addEventListener('click', saveConfig);
    $('#btnTestEmail').addEventListener('click', sendTestEmail);
    driverEl.addEventListener('change', toggleSections);
    configureBtn.addEventListener('click', () => {
        if (!hasBillingAccess()) {
            requireBillingAccess(() => openModal(), () => loadConfig(() => {
                openModal();
            }));
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

    loadAccessPolicy();
    updateBillingStatusAction();
    setNotificationsLocked(true);
    if (unlockNotificationsBtn) unlockNotificationsBtn.addEventListener('click', requestNotificationsAccess);

    // Lab Station ops state
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const guacamoleCandidateListEl = $('#guacamoleCandidateList');
    const refreshPowerControllersBtn = $('#refreshPowerControllersBtn');
    const powerControllerListEl = $('#powerControllerList');
    const powerControllersStatusEl = $('#powerControllersStatus');
    const powerControllersHintEl = $('#powerControllersHint');
    const powerControllerSelectEl = $('#powerControllerSelect');
    const powerControllerIdEl = $('#powerControllerId');
    const powerControllerNameEl = $('#powerControllerName');
    const powerControllerDriverEl = $('#powerControllerDriver');
    const powerControllerEnabledEl = $('#powerControllerEnabled');
    const powerControllerHostEl = $('#powerControllerHost');
    const powerControllerPortEl = $('#powerControllerPort');
    const powerControllerCredentialRefEl = $('#powerControllerCredentialRef');
    const powerControllerNetioPathEl = $('#powerControllerNetioPath');
    const powerControllerNetioHttpsEl = $('#powerControllerNetioHttps');
    const powerControllerNetioVerifyTlsEl = $('#powerControllerNetioVerifyTls');
    const powerControllerNetioPathFieldEl = $('#powerControllerNetioPathField');
    const powerControllerNetioHttpsFieldEl = $('#powerControllerNetioHttpsField');
    const powerControllerNetioVerifyTlsFieldEl = $('#powerControllerNetioVerifyTlsField');
    const powerControllerProfileFieldEl = $('#powerControllerProfileField');
    const powerControllerSnmpVersionFieldEl = $('#powerControllerSnmpVersionField');
    const powerControllerProfileEl = $('#powerControllerProfile');
    const powerControllerSnmpVersionEl = $('#powerControllerSnmpVersion');
    const powerControllerTimeoutSecondsEl = $('#powerControllerTimeoutSeconds');
    const powerControllerRetriesEl = $('#powerControllerRetries');
    const powerControllerOutletsEl = $('#powerControllerOutlets');
    const addPowerControllerOutletBtn = $('#addPowerControllerOutletBtn');
    const savePowerControllerBtn = $('#savePowerControllerBtn');
    const powerControllerEditorHintEl = $('#powerControllerEditorHint');
    const refreshPowerCredentialsBtn = $('#refreshPowerCredentialsBtn');
    const powerCredentialsListEl = $('#powerCredentialsList');
    const powerCredentialsStatusEl = $('#powerCredentialsStatus');
    const powerCredentialsHintEl = $('#powerCredentialsHint');
    const powerCredentialSelectEl = $('#powerCredentialSelect');
    const powerCredentialRefEl = $('#powerCredentialRef');
    const powerCredentialTypeEl = $('#powerCredentialType');
    const powerCredentialUsernameEl = $('#powerCredentialUsername');
    const powerCredentialPasswordEl = $('#powerCredentialPassword');
    const powerCredentialCommunityEl = $('#powerCredentialCommunity');
    const powerCredentialAuthProtocolEl = $('#powerCredentialAuthProtocol');
    const powerCredentialAuthPasswordEl = $('#powerCredentialAuthPassword');
    const powerCredentialPrivProtocolEl = $('#powerCredentialPrivProtocol');
    const powerCredentialPrivPasswordEl = $('#powerCredentialPrivPassword');
    const powerCredentialContextNameEl = $('#powerCredentialContextName');
    const powerCredentialUsernameFieldEl = $('#powerCredentialUsernameField');
    const powerCredentialPasswordFieldEl = $('#powerCredentialPasswordField');
    const powerCredentialCommunityFieldEl = $('#powerCredentialCommunityField');
    const powerCredentialAuthProtocolFieldEl = $('#powerCredentialAuthProtocolField');
    const powerCredentialAuthPasswordFieldEl = $('#powerCredentialAuthPasswordField');
    const powerCredentialPrivProtocolFieldEl = $('#powerCredentialPrivProtocolField');
    const powerCredentialPrivPasswordFieldEl = $('#powerCredentialPrivPasswordField');
    const powerCredentialContextNameFieldEl = $('#powerCredentialContextNameField');
    const powerCredentialSaveBtn = $('#powerCredentialSaveBtn');
    const powerCredentialEditorHintEl = $('#powerCredentialEditorHint');
    const powerOperationReasonEl = $('#powerOperationReason');
    const powerCycleSecondsEl = $('#powerCycleSeconds');
    const powerMaintenanceModeEl = $('#powerMaintenanceMode');
    const powerPolicySelectEl = $('#powerPolicySelect');
    const powerPolicyLabSelectEl = $('#powerPolicyLabSelect');
    const powerPolicyNameEl = $('#powerPolicyName');
    const powerPolicyEnabledEl = $('#powerPolicyEnabled');
    const powerPolicyRespectLocalModeEl = $('#powerPolicyRespectLocalMode');
    const powerPolicyMaintenanceModeEl = $('#powerPolicyMaintenanceMode');
    const powerPolicyStartFailureModeEl = $('#powerPolicyStartFailureMode');
    const powerPolicyEndFailureModeEl = $('#powerPolicyEndFailureMode');
    const powerPolicyStepsEl = $('#powerPolicySteps');
    const addPowerPolicyStepBtn = $('#addPowerPolicyStepBtn');
    const savePowerPolicyBtn = $('#savePowerPolicyBtn');
    const powerPoliciesStatusEl = $('#powerPoliciesStatus');
    const powerPolicyEditorHintEl = $('#powerPolicyEditorHint');
    const hostState = {};
    const hostMetadata = {};
    const guacamoleCandidateState = {};
    const heartbeatSources = {};
    let powerControllers = [];
    let powerControllerOutletDrafts = [];
    let lastPowerControllerDriver = 'mock';
    let powerCredentials = [];
    let powerPolicies = [];
    let powerPolicyStepDrafts = [];
    let managedLabsInitialized = false;
    let hostNames = [];
    let guacamoleCandidates = [];

    // FMU AAS sync elements
    const fmuSyncBtn = $('#fmuSyncBtn');
    const fmuSyncKeyEl = $('#fmuSyncKey');
    const fmuSyncLabSelectEl = $('#fmuSyncLabSelect');
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
        fmuSyncKeyEl.addEventListener('input', () => {
            // User is editing the key — clear any previous auto-filled locks
            _clearAllFmuHints();
        });
    }

    if (fmuSyncKeyEl) {
        fmuSyncKeyEl.addEventListener('change', () => {
            const key = fmuSyncKeyEl.value.trim();
            if (!key) { _clearAllFmuHints(); return; }
            _fetchFmuHints(key);
        });
    }

    if (fmuSyncBtn) {
        fmuSyncBtn.addEventListener('click', () => {
            const accessKey = (fmuSyncKeyEl && fmuSyncKeyEl.value || '').trim();
            const labId = (fmuSyncLabSelectEl && fmuSyncLabSelectEl.value || '').trim();
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
    const aasLinkLabSelectEl = $('#aasLinkLabSelect');
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
            const labId = (aasLinkLabSelectEl && aasLinkLabSelectEl.value || '').trim();
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
                if (aasLinkLabSelectEl) aasLinkLabSelectEl.value = data.labId || '';
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
    const upcomingReservationsListEl = $('#upcomingReservationsList');
    const upcomingReservationsStatusEl = $('#upcomingReservationsStatus');
    const TIMELINE_DEFAULT_LIMIT = 100;
    const ACTIONABLE_RESERVATIONS_PAGE_SIZE = 100;
    const timelineState = {
        reservationId: null,
        limit: TIMELINE_DEFAULT_LIMIT,
        operations: [],
        base: null,
        pagination: null,
        nextOffset: 0,
        loading: false
    };
    const actionableReservationsState = {
        reservations: [],
        offset: 0,
        nextOffset: 0,
        cursor: null,
        total: null,
        totalKnown: false,
        hasMore: false,
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
    }
    if (powerControllerListEl) powerControllerListEl.addEventListener('click', handlePowerActions);
    if (refreshPowerControllersBtn) refreshPowerControllersBtn.addEventListener('click', loadPowerControllers);
    if (powerControllerSelectEl) powerControllerSelectEl.addEventListener('change', loadSelectedPowerController);
    if (powerControllerDriverEl) powerControllerDriverEl.addEventListener('change', updatePowerControllerDriverFields);
    if (powerControllerNetioHttpsEl) powerControllerNetioHttpsEl.addEventListener('change', updatePowerControllerNetioPort);
    if (addPowerControllerOutletBtn) addPowerControllerOutletBtn.addEventListener('click', addPowerControllerOutlet);
    if (powerControllerOutletsEl) {
        powerControllerOutletsEl.addEventListener('change', handlePowerControllerOutletChange);
        powerControllerOutletsEl.addEventListener('input', handlePowerControllerOutletChange);
        powerControllerOutletsEl.addEventListener('click', handlePowerControllerOutletActions);
    }
    if (savePowerControllerBtn) savePowerControllerBtn.addEventListener('click', savePowerController);
    if (refreshPowerCredentialsBtn) refreshPowerCredentialsBtn.addEventListener('click', loadPowerCredentials);
    if (powerCredentialSelectEl) powerCredentialSelectEl.addEventListener('change', loadSelectedPowerCredential);
    if (powerCredentialTypeEl) powerCredentialTypeEl.addEventListener('change', updatePowerCredentialFields);
    if (powerCredentialAuthProtocolEl) powerCredentialAuthProtocolEl.addEventListener('change', updatePowerCredentialFields);
    if (powerCredentialPrivProtocolEl) powerCredentialPrivProtocolEl.addEventListener('change', updatePowerCredentialFields);
    if (powerCredentialSaveBtn) powerCredentialSaveBtn.addEventListener('click', savePowerCredential);
    if (powerCredentialsListEl) powerCredentialsListEl.addEventListener('click', handlePowerCredentialActions);
    updatePowerCredentialFields();
    if (powerPolicySelectEl) powerPolicySelectEl.addEventListener('change', loadSelectedPowerPolicy);
    if (powerPolicyLabSelectEl) powerPolicyLabSelectEl.addEventListener('change', handlePowerPolicyLabChange);
    if (addPowerPolicyStepBtn) addPowerPolicyStepBtn.addEventListener('click', addPowerPolicyStep);
    if (powerPolicyStepsEl) {
        powerPolicyStepsEl.addEventListener('change', handlePowerPolicyStepChange);
        powerPolicyStepsEl.addEventListener('input', handlePowerPolicyStepChange);
        powerPolicyStepsEl.addEventListener('click', handlePowerPolicyStepActions);
    }
    if (savePowerPolicyBtn) savePowerPolicyBtn.addEventListener('click', savePowerPolicy);
    if (powerPolicyNameEl && !powerPolicyNameEl.value) resetPowerPolicyEditor();
    if (guacamoleCandidateListEl) {
        guacamoleCandidateListEl.addEventListener('click', handleGuacamoleCandidateActions);
    }

    function loadConfig(onSuccess) {
        setStatus('Loading...');
        updateBillingStatusAction();
        if (billingAccessPromise) {
            return billingAccessPromise.then(accessReady => {
                if (accessReady && typeof onSuccess === 'function') onSuccess();
                return accessReady;
            });
        }

        const request = fetch('/billing/admin/notifications', {
            credentials: 'include',
            // Billing is requested only when its configuration is used, not
            // as a second authentication prompt during page loading.
            skipAuthPrompt: true
        })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                billingAccessReady = true;
                billingTokenRequired = false;
                const cfg = data.config || {};
                applyNotificationConfig(cfg);
                setNotificationsLocked(false);
                setStatus('Loaded');
                updateBillingStatusAction();
                showToast('Configuration loaded', 'success');
                if (typeof onSuccess === 'function') {
                    onSuccess();
                }
                return true;
            })
            .catch(err => {
                billingAccessReady = false;
                const needsToken = err.message === 'HTTP 401';
                if (!needsToken) console.error(err);
                billingTokenRequired = needsToken;
                setNotificationsLocked(true);
                setStatus(needsToken ? 'Gateway administrator token required' : 'Error');
                updateBillingStatusAction();
                showToast(needsToken ? 'Enter the Gateway administrator token to load notifications' : 'Cannot load config (check administrator access)', 'error');
                return false;
            });

        let pending;
        pending = request.finally(() => {
            if (billingAccessPromise === pending) billingAccessPromise = null;
        });
        billingAccessPromise = pending;
        return pending.then(accessReady => {
            if (accessReady && typeof onSuccess === 'function') onSuccess();
            return accessReady;
        });
    }

    function applyNotificationConfig(cfg) {
        enabledEl.checked = !!cfg.enabled;
        driverEl.value = cfg.driver || 'NOOP';
        fromEl.value = cfg.from || '';
        fromNameEl.value = cfg.fromName || '';
        defaultToEl.value = (cfg.defaultTo || []).join(', ');
        setTimezone(cfg.timezone || browserTimezone);
        const smtp = cfg.smtp || {};
        smtpHostEl.value = smtp.host || '';
        smtpPortEl.value = smtp.port || '';
        smtpUserEl.value = smtp.username || '';
        smtpPassEl.value = '';
        smtpStartTlsEl.checked = smtp.startTls ?? true;
        if (smtpPasswordHintEl) {
            smtpPasswordHintEl.textContent = smtp.passwordConfigured
                ? 'A password is stored. Leave blank to keep it.'
                : 'No password is currently stored.';
        }
        const graph = cfg.graph || {};
        graphTenantEl.value = graph.tenantId || '';
        graphClientIdEl.value = graph.clientId || '';
        graphClientSecretEl.value = '';
        graphFromEl.value = graph.from || '';
        if (graphClientSecretHintEl) {
            graphClientSecretHintEl.textContent = graph.clientSecretConfigured
                ? 'A client secret is stored. Leave blank to keep it.'
                : 'No client secret is currently stored.';
        }
        toggleSections();
        updateDriverSummary();
    }

    function setNotificationsLocked(locked) {
        if (notificationsAccessGateEl) notificationsAccessGateEl.hidden = !locked;
        if (notificationsConfigContentEl) notificationsConfigContentEl.hidden = locked;
        [configureBtn, $('#btnTestLoad'), $('#saveConfigBtn'), $('#btnTestEmail')]
            .filter(Boolean)
            .forEach(button => { button.disabled = locked; });
    }

    function requestNotificationsAccess() {
        loadConfig().then(accessReady => {
            if (!accessReady && billingTokenRequired) {
                promptBillingToken(() => loadConfig());
            }
        });
    }

    if (upcomingReservationsListEl) {
        upcomingReservationsListEl.addEventListener('click', handleUpcomingReservationActions);
    }

    const initializedManagerTabs = new Set();
    document.addEventListener('lab-manager:tab-activated', event => {
        initializeManagerTab(event.detail && event.detail.tab);
    });
    if (window.LabManagerTabs && window.LabManagerTabs.activeTab) {
        initializeManagerTab(window.LabManagerTabs.activeTab);
    }

    function initializeManagerTab(tabName) {
        if (!tabName || initializedManagerTabs.has(tabName)) return;
        initializedManagerTabs.add(tabName);

        if (tabName === 'operations') {
            checkOpsAvailability();
            if (hostListEl) loadHostInventory({ skipAuthPrompt: true });
            if (upcomingReservationsListEl) loadActionableReservations();
            loadActivityFeed(false);
            return;
        }
        if (tabName === 'energy') {
            if (powerControllerListEl || powerControllerSelectEl) loadPowerControllers({ skipAuthPrompt: true });
            if (powerCredentialsListEl || powerCredentialSelectEl) loadPowerCredentials({ skipAuthPrompt: true });
            if (powerPolicyLabSelectEl) loadManagedLabsOnce();
            if (powerPolicySelectEl) loadPowerPolicies({ skipAuthPrompt: true });
            return;
        }
        if (tabName === 'digital-twins') {
            if (fmuSyncKeyEl || fmuSyncLabSelectEl || aasLinkLabSelectEl) {
                loadManagedLabsOnce();
            }
            return;
        }
        if (tabName === 'notifications') {
            requestNotificationsAccess();
        }
    }

    function loadManagedLabsOnce() {
        if (managedLabsInitialized) return;
        managedLabsInitialized = true;
        loadManagedLabs({ skipAuthPrompt: true });
    }

    function requireBillingAccess(onAuthenticated, onTokenAuthenticated) {
        if (hasBillingAccess()) {
            if (typeof onAuthenticated === 'function') onAuthenticated();
            return;
        }

        loadConfig().then(accessReady => {
            if (accessReady) {
                if (typeof onAuthenticated === 'function') onAuthenticated();
                return;
            }
            if (billingTokenRequired) {
                promptBillingToken(onTokenAuthenticated || onAuthenticated);
            }
        });
    }

    function saveConfig() {
        if (!hasBillingAccess()) {
            requireBillingAccess(() => saveConfig());
            return;
        }

        const smtpPassword = smtpPassEl.value.trim();
        const graphClientSecret = graphClientSecretEl.value.trim();
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
                startTls: smtpStartTlsEl.checked
            },
            graph: {
                tenantId: graphTenantEl.value.trim(),
                clientId: graphClientIdEl.value.trim(),
                from: graphFromEl.value.trim()
            }
        };
        if (smtpPassword) payload.smtp.password = smtpPassword;
        if (graphClientSecret) payload.graph.clientSecret = graphClientSecret;

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
            .then(data => {
                applyNotificationConfig(data.config || {
                    ...payload,
                    smtp: { ...payload.smtp, passwordConfigured: Boolean(smtpPassword) },
                    graph: { ...payload.graph, clientSecretConfigured: Boolean(graphClientSecret) }
                });
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
                key: 'billing',
                login: '/admin/login',
                header: 'X-Access-Token',
                cookie: 'access_token',
                title: 'Gateway administrator token required',
                description: 'Enter the Gateway administrator token for Wallet & Billing.',
                invalidMessage: 'Invalid Gateway administrator token.'
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
        configStatusEl.title = needsToken ? 'Click to enter the Gateway administrator token' : '';
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
            requireBillingAccess(() => sendTestEmail());
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
                badge.textContent = 'Lab Manager session required';
                badge.classList.remove('local', 'private', 'external', 'token-required-action');
                return;
            }
            if (res.status === 403) {
                badge.textContent = 'Access Policy Blocked';
                badge.classList.remove('local', 'private', 'external', 'token-required-action');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const status = await res.json();
            updateAccessPolicyBadge(status);
        } catch (err) {
            badge.textContent = 'Access Policy Unavailable';
            badge.classList.remove('local', 'private', 'external', 'token-required-action');
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

        badge.classList.remove('local', 'private', 'external', 'token-required-action');
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
    async function loadHostInventory(options = {}) {
        try {
            const res = await fetch('/ops/api/hosts', options);
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) {
                    showToast('Lab Manager session required to load Lab Station hosts', 'error');
                }
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

    async function loadPowerControllers(options = {}) {
        if (powerControllersStatusEl) {
            powerControllersStatusEl.textContent = 'Loading...';
            powerControllersStatusEl.className = 'pill soft';
        }
        try {
            const res = await fetch('/ops/api/power/controllers', options);
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power controllers', 'error');
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            powerControllers = Array.isArray(body.controllers) ? body.controllers : [];
            renderPowerControllers();
            renderPowerControllerOptions();
            renderPowerPolicySteps();
            if (powerControllersStatusEl) {
                powerControllersStatusEl.textContent = `${powerControllers.length} controller${powerControllers.length === 1 ? '' : 's'}`;
                powerControllersStatusEl.className = 'pill good';
            }
            if (powerControllersHintEl) {
                powerControllersHintEl.textContent = powerControllers.length
                    ? 'Protected outlets require an explicit maintenance mode toggle. Physical activation remains subject to provider hardware validation.'
                    : 'No controller is configured. Add one to the provider-local power catalog before using this panel.';
            }
        } catch (err) {
            console.warn('Unable to load power controllers', err);
            powerControllers = [];
            renderPowerControllers();
            renderPowerControllerOptions();
            renderPowerPolicySteps();
            if (powerControllersStatusEl) {
                powerControllersStatusEl.textContent = 'Unavailable';
                powerControllersStatusEl.className = 'pill bad';
            }
            if (powerControllersHintEl) powerControllersHintEl.textContent = 'Power controllers could not be loaded.';
        }
    }

    function updatePowerCredentialFields() {
        const type = powerCredentialTypeEl?.value || 'netio-http-basic';
        const isNetio = type === 'netio-http-basic';
        const isSnmpV1V2 = type === 'snmpv1' || type === 'snmpv2c';
        const isSnmpV3 = type === 'snmpv3';
        const authProtocol = powerCredentialAuthProtocolEl?.value || 'NONE';
        const privProtocol = powerCredentialPrivProtocolEl?.value || 'NONE';
        if (powerCredentialUsernameFieldEl) powerCredentialUsernameFieldEl.hidden = isSnmpV1V2;
        if (powerCredentialPasswordFieldEl) powerCredentialPasswordFieldEl.hidden = !isNetio;
        if (powerCredentialCommunityFieldEl) powerCredentialCommunityFieldEl.hidden = !isSnmpV1V2;
        if (powerCredentialAuthProtocolFieldEl) powerCredentialAuthProtocolFieldEl.hidden = !isSnmpV3;
        if (powerCredentialAuthPasswordFieldEl) powerCredentialAuthPasswordFieldEl.hidden = !isSnmpV3 || authProtocol === 'NONE';
        if (powerCredentialPrivProtocolFieldEl) powerCredentialPrivProtocolFieldEl.hidden = !isSnmpV3;
        if (powerCredentialPrivPasswordFieldEl) powerCredentialPrivPasswordFieldEl.hidden = !isSnmpV3 || privProtocol === 'NONE';
        if (powerCredentialContextNameFieldEl) powerCredentialContextNameFieldEl.hidden = !isSnmpV3;
    }

    function resetPowerCredentialEditor() {
        if (powerCredentialSelectEl) powerCredentialSelectEl.value = '';
        if (powerCredentialRefEl) {
            powerCredentialRefEl.value = '';
            powerCredentialRefEl.disabled = false;
        }
        if (powerCredentialTypeEl) {
            powerCredentialTypeEl.value = 'netio-http-basic';
            powerCredentialTypeEl.disabled = false;
        }
        [
            powerCredentialUsernameEl,
            powerCredentialPasswordEl,
            powerCredentialCommunityEl,
            powerCredentialAuthPasswordEl,
            powerCredentialPrivPasswordEl,
            powerCredentialContextNameEl,
        ].forEach(element => {
            if (element) element.value = '';
        });
        if (powerCredentialAuthProtocolEl) powerCredentialAuthProtocolEl.value = 'NONE';
        if (powerCredentialPrivProtocolEl) powerCredentialPrivProtocolEl.value = 'NONE';
        updatePowerCredentialFields();
        if (powerCredentialEditorHintEl) powerCredentialEditorHintEl.textContent = 'Configure a new provider-local credential.';
    }

    function populatePowerCredentialForm(credential) {
        if (powerCredentialRefEl) {
            powerCredentialRefEl.value = credential.credentialRef || '';
            powerCredentialRefEl.disabled = true;
        }
        if (powerCredentialTypeEl) {
            powerCredentialTypeEl.value = credential.type || 'netio-http-basic';
            powerCredentialTypeEl.disabled = true;
        }
        [
            powerCredentialUsernameEl,
            powerCredentialPasswordEl,
            powerCredentialCommunityEl,
            powerCredentialAuthPasswordEl,
            powerCredentialPrivPasswordEl,
            powerCredentialContextNameEl,
        ].forEach(element => {
            if (element) element.value = '';
        });
        if (powerCredentialAuthProtocolEl) powerCredentialAuthProtocolEl.value = 'NONE';
        if (powerCredentialPrivProtocolEl) powerCredentialPrivProtocolEl.value = 'NONE';
        updatePowerCredentialFields();
        if (powerCredentialEditorHintEl) powerCredentialEditorHintEl.textContent = 'Enter replacement secret values to rotate this credential. The current values are never loaded.';
    }

    function renderPowerCredentialOptions() {
        if (!powerCredentialSelectEl) return;
        const current = powerCredentialSelectEl.value;
        powerCredentialSelectEl.innerHTML = '<option value="">New credential</option>';
        powerCredentials.forEach(credential => {
            const option = document.createElement('option');
            option.value = credential.credentialRef || '';
            option.textContent = `${credential.credentialRef || 'unknown'} · ${credential.type || 'unknown'}`;
            powerCredentialSelectEl.appendChild(option);
        });
        const selected = powerCredentials.some(item => String(item.credentialRef) === String(current)) ? current : '';
        powerCredentialSelectEl.value = selected;
        if (selected) loadSelectedPowerCredential();
        else resetPowerCredentialEditor();
    }

    function loadSelectedPowerCredential() {
        const reference = powerCredentialSelectEl?.value || '';
        const credential = powerCredentials.find(item => String(item.credentialRef || '') === String(reference));
        if (credential) populatePowerCredentialForm(credential);
        else resetPowerCredentialEditor();
    }

    function renderPowerCredentials() {
        if (!powerCredentialsListEl) return;
        if (!powerCredentials.length) {
            powerCredentialsListEl.innerHTML = '<div class="empty">No energy credentials are configured.</div>';
            return;
        }
        powerCredentialsListEl.innerHTML = powerCredentials.map(credential => `
            <div class="power-controller-row">
                <div>
                    <strong>${escapeHtml(credential.credentialRef || 'unknown')}</strong>
                    <div class="host-meta">Type: ${escapeHtml(credential.type || 'unknown')} · Secret values hidden</div>
                </div>
                <button class="mini-btn" type="button" data-power-credential-ref="${escapeHtml(credential.credentialRef || '')}">Rotate</button>
            </div>
        `).join('');
    }

    function handlePowerCredentialActions(event) {
        const button = event.target?.closest?.('[data-power-credential-ref]');
        const reference = button?.dataset?.powerCredentialRef;
        if (!reference || !powerCredentialSelectEl) return;
        powerCredentialSelectEl.value = reference;
        loadSelectedPowerCredential();
    }

    function readPowerCredentialForm() {
        const credentialRef = (powerCredentialRefEl?.value || '').trim().toLowerCase();
        const type = (powerCredentialTypeEl?.value || '').trim().toLowerCase();
        if (!credentialRef) throw new Error('Credential reference is required');
        if (!/^[a-z0-9][a-z0-9._:-]{0,127}$/.test(credentialRef)) throw new Error('Credential reference contains invalid characters');
        if (!['netio-http-basic', 'snmpv1', 'snmpv2c', 'snmpv3'].includes(type)) throw new Error('Select a supported credential type');

        let credentials;
        if (type === 'netio-http-basic') {
            const username = (powerCredentialUsernameEl?.value || '').trim();
            const password = powerCredentialPasswordEl?.value || '';
            if (!username || !password) throw new Error('NETIO username and password are required');
            credentials = { username, password };
        } else if (type === 'snmpv1' || type === 'snmpv2c') {
            const community = powerCredentialCommunityEl?.value || '';
            if (!community) throw new Error('SNMP community is required');
            credentials = { version: type.slice(4), community };
        } else {
            const username = (powerCredentialUsernameEl?.value || '').trim();
            const authProtocol = powerCredentialAuthProtocolEl?.value || 'NONE';
            const privProtocol = powerCredentialPrivProtocolEl?.value || 'NONE';
            if (!username) throw new Error('SNMPv3 username is required');
            if (privProtocol !== 'NONE' && authProtocol === 'NONE') throw new Error('SNMPv3 privacy requires authentication');
            credentials = { version: 'v3', username, authProtocol, privProtocol };
            if (authProtocol !== 'NONE') {
                const authPassword = powerCredentialAuthPasswordEl?.value || '';
                if (!authPassword) throw new Error('SNMPv3 authentication password is required');
                credentials.authPassword = authPassword;
            }
            if (privProtocol !== 'NONE') {
                const privPassword = powerCredentialPrivPasswordEl?.value || '';
                if (!privPassword) throw new Error('SNMPv3 privacy password is required');
                credentials.privPassword = privPassword;
            }
            const contextName = (powerCredentialContextNameEl?.value || '').trim();
            if (contextName) credentials.contextName = contextName;
        }
        return {
            credentialRef,
            type,
            credentials,
            overwrite: Boolean(powerCredentialSelectEl?.value),
        };
    }

    async function loadPowerCredentials(options = {}) {
        if (powerCredentialsStatusEl) {
            powerCredentialsStatusEl.textContent = 'Loading...';
            powerCredentialsStatusEl.className = 'pill soft';
        }
        try {
            const res = await fetch('/ops/api/power/credentials', options);
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load energy credentials', 'error');
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            powerCredentials = Array.isArray(body.credentials) ? body.credentials : [];
            renderPowerCredentials();
            renderPowerCredentialOptions();
            if (powerCredentialsStatusEl) {
                powerCredentialsStatusEl.textContent = `${powerCredentials.length} credential${powerCredentials.length === 1 ? '' : 's'}`;
                powerCredentialsStatusEl.className = 'pill good';
            }
            if (powerCredentialsHintEl) powerCredentialsHintEl.textContent = powerCredentials.length
                ? 'Secret values are write-only. Select a reference to rotate it.'
                : 'No energy credentials are configured.';
        } catch (err) {
            console.warn('Unable to load power credentials', err);
            powerCredentials = [];
            renderPowerCredentials();
            renderPowerCredentialOptions();
            if (powerCredentialsStatusEl) {
                powerCredentialsStatusEl.textContent = 'Unavailable';
                powerCredentialsStatusEl.className = 'pill bad';
            }
            if (powerCredentialsHintEl) powerCredentialsHintEl.textContent = 'Energy credentials could not be loaded.';
        }
    }

    async function savePowerCredential() {
        let credential;
        try {
            credential = readPowerCredentialForm();
        } catch (err) {
            showToast(`Energy credential is invalid: ${err.message}`, 'error');
            return;
        }
        if (powerCredentialSaveBtn) powerCredentialSaveBtn.disabled = true;
        try {
            const res = await fetch('/ops/api/power/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(credential),
            });
            const body = await res.json().catch(() => ({}));
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) throw new Error('Lab Manager session required');
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            showToast(`${credential.overwrite ? 'Energy credential rotated' : 'Energy credential saved'}: ${credential.credentialRef}`, 'success');
            await loadPowerCredentials({ skipAuthPrompt: true });
            if (powerCredentialSelectEl) powerCredentialSelectEl.value = credential.credentialRef;
            loadSelectedPowerCredential();
        } catch (err) {
            showToast(`Energy credential save failed: ${err.message}`, 'error');
        } finally {
            if (powerCredentialSaveBtn) powerCredentialSaveBtn.disabled = false;
        }
    }

    async function loadManagedLabs(options = {}) {
        if (!powerPolicyLabSelectEl && !fmuSyncKeyEl && !fmuSyncLabSelectEl && !aasLinkLabSelectEl) return;
        const selectedPowerPolicyLabId = powerPolicyLabSelectEl?.value || '';
        const selectedFmuAccessKey = fmuSyncKeyEl?.value || '';
        const selectedFmuLabId = fmuSyncLabSelectEl?.value || '';
        const selectedAasLinkLabId = aasLinkLabSelectEl?.value || '';
        try {
            const res = await fetch('/lab-admin/labs', options);
            if (res.status === 403) {
                showOpsWarning();
                renderPowerPolicyLabOptions([]);
                renderFmuAccessKeyOptions([]);
                renderFmuLabOptions(fmuSyncLabSelectEl, []);
                renderFmuLabOptions(aasLinkLabSelectEl, []);
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load laboratories', 'error');
                renderPowerPolicyLabOptions([]);
                renderFmuAccessKeyOptions([]);
                renderFmuLabOptions(fmuSyncLabSelectEl, []);
                renderFmuLabOptions(aasLinkLabSelectEl, []);
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            renderPowerPolicyLabOptions(body.labs, selectedPowerPolicyLabId);
            renderFmuAccessKeyOptions(body.labs, selectedFmuAccessKey);
            renderFmuLabOptions(fmuSyncLabSelectEl, body.labs, selectedFmuLabId);
            renderFmuLabOptions(aasLinkLabSelectEl, body.labs, selectedAasLinkLabId);
        } catch (err) {
            console.warn('Unable to load provider laboratories', err);
            renderPowerPolicyLabOptions([]);
            renderFmuAccessKeyOptions([]);
            renderFmuLabOptions(fmuSyncLabSelectEl, []);
            renderFmuLabOptions(aasLinkLabSelectEl, []);
        }
    }

    function renderPowerPolicyLabOptions(labs, preferredLabId = '') {
        if (!powerPolicyLabSelectEl) return;
        const current = powerPolicyLabSelectEl.value;
        const validLabs = (Array.isArray(labs) ? labs : [])
            .filter(lab => String(lab?.labId || '').trim())
            .filter((lab, index, items) => items.findIndex(item => String(item.labId) === String(lab.labId)) === index);
        powerPolicyLabSelectEl.innerHTML = validLabs.length
            ? '<option value="">Select a laboratory</option>'
            : '<option value="">No laboratories available</option>';
        validLabs.forEach(lab => {
            const labId = String(lab.labId).trim();
            const option = document.createElement('option');
            option.value = labId;
            option.textContent = formatPowerPolicyLabLabel(lab);
            powerPolicyLabSelectEl.appendChild(option);
        });
        const selected = preferredLabId || current || powerPolicySelectEl?.value || '';
        powerPolicyLabSelectEl.value = validLabs.some(lab => String(lab.labId) === selected)
            ? selected
            : '';
        powerPolicyLabSelectEl.disabled = validLabs.length === 0;
    }

    function renderFmuLabOptions(selectEl, labs, preferredLabId = '') {
        if (!selectEl) return;
        const current = selectEl.value;
        const fmuLabs = (Array.isArray(labs) ? labs : [])
            .filter(lab => Number(lab?.resourceType) === 1)
            .filter(lab => String(lab?.labId || '').trim())
            .filter((lab, index, items) => items.findIndex(item => String(item.labId) === String(lab.labId)) === index);
        selectEl.innerHTML = fmuLabs.length
            ? '<option value="">No lab ID override</option>'
            : '<option value="">No FMU laboratories available</option>';
        fmuLabs.forEach(lab => {
            const labId = String(lab.labId).trim();
            const option = document.createElement('option');
            option.value = labId;
            option.textContent = formatPowerPolicyLabLabel(lab);
            selectEl.appendChild(option);
        });
        const selected = preferredLabId || current || '';
        selectEl.value = fmuLabs.some(lab => String(lab.labId) === selected)
            ? selected
            : '';
        selectEl.disabled = fmuLabs.length === 0;
    }

    function renderFmuAccessKeyOptions(labs, preferredAccessKey = '') {
        if (!fmuSyncKeyEl) return;
        const current = fmuSyncKeyEl.value;
        const accessKeys = (Array.isArray(labs) ? labs : [])
            .filter(lab => Number(lab?.resourceType) === 1)
            .filter(lab => String(lab?.accessKey || '').trim())
            .filter((lab, index, items) => items.findIndex(item => String(item.accessKey) === String(lab.accessKey)) === index);
        fmuSyncKeyEl.innerHTML = accessKeys.length
            ? '<option value="">Select an FMU access key</option>'
            : '<option value="">No FMU access keys available</option>';
        accessKeys.forEach(lab => {
            const accessKey = String(lab.accessKey).trim();
            const option = document.createElement('option');
            option.value = accessKey;
            option.textContent = `Lab #${String(lab.labId).trim()} · ${accessKey}`;
            fmuSyncKeyEl.appendChild(option);
        });
        const selected = preferredAccessKey || current || '';
        fmuSyncKeyEl.value = accessKeys.some(lab => String(lab.accessKey) === selected)
            ? selected
            : '';
        fmuSyncKeyEl.disabled = accessKeys.length === 0;
    }

    function formatPowerPolicyLabLabel(lab) {
        const labId = String(lab?.labId || '').trim();
        const resourceType = Number(lab?.resourceType) === 1 ? 'FMU' : 'Remote';
        const status = lab?.listed ? 'Listed' : 'Draft';
        return `Lab #${labId} · ${resourceType} · ${status}`;
    }

    function handlePowerPolicyLabChange() {
        const labId = powerPolicyLabSelectEl?.value || '';
        if (powerPolicySelectEl) {
            powerPolicySelectEl.value = powerPolicies.some(policy => String(policy.labId || '') === labId)
                ? labId
                : '';
        }
        loadSelectedPowerPolicy();
    }

    async function loadPowerPolicies(options = {}) {
        if (powerPoliciesStatusEl) {
            powerPoliciesStatusEl.textContent = 'Loading...';
            powerPoliciesStatusEl.className = 'pill soft';
        }
        try {
            const selectedLabId = powerPolicyLabSelectEl?.value || powerPolicySelectEl?.value || '';
            const res = await fetch('/ops/api/power/policies', options);
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power policies', 'error');
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            powerPolicies = Array.isArray(body.policies) ? body.policies : [];
            renderPowerPolicyOptions(selectedLabId);
            if (powerPoliciesStatusEl) {
                powerPoliciesStatusEl.textContent = `${powerPolicies.length} polic${powerPolicies.length === 1 ? 'y' : 'ies'}`;
                powerPoliciesStatusEl.className = 'pill good';
            }
        } catch (err) {
            console.warn('Unable to load power policies', err);
            powerPolicies = [];
            renderPowerPolicyOptions('');
            if (powerPoliciesStatusEl) {
                powerPoliciesStatusEl.textContent = 'Unavailable';
                powerPoliciesStatusEl.className = 'pill bad';
            }
            if (powerPolicyEditorHintEl) powerPolicyEditorHintEl.textContent = 'Power policies could not be loaded.';
        }
    }

    function renderPowerPolicyOptions(preferredLabId) {
        if (!powerPolicySelectEl) return;
        const current = powerPolicySelectEl.value;
        powerPolicySelectEl.innerHTML = '<option value="">New policy</option>';
        powerPolicies.forEach(policy => {
            const option = document.createElement('option');
            option.value = policy.labId || '';
            option.textContent = `${policy.labId || 'unknown'} · ${policy.policyName || 'Unnamed policy'}`;
            powerPolicySelectEl.appendChild(option);
        });
        const selected = preferredLabId || current;
        if (selected && powerPolicies.some(policy => String(policy.labId) === selected)) {
            powerPolicySelectEl.value = selected;
        } else {
            powerPolicySelectEl.value = '';
        }
        loadSelectedPowerPolicy();
    }

    function loadSelectedPowerPolicy() {
        const labId = powerPolicySelectEl?.value || '';
        const policy = powerPolicies.find(item => String(item.labId || '') === labId);
        if (policy) {
            if (powerPolicyLabSelectEl) powerPolicyLabSelectEl.value = policy.labId || '';
            populatePowerPolicyForm(policy);
            if (powerPolicyEditorHintEl) powerPolicyEditorHintEl.textContent = 'Edit the policy and save it to the provider-local catalog.';
            return;
        }
        resetPowerPolicyEditor(false);
    }

    function resetPowerPolicyEditor(clearLabId = true) {
        if (clearLabId && powerPolicyLabSelectEl) powerPolicyLabSelectEl.value = '';
        if (powerPolicyNameEl) powerPolicyNameEl.value = 'New lab policy';
        if (powerPolicyEnabledEl) powerPolicyEnabledEl.checked = true;
        if (powerPolicyRespectLocalModeEl) powerPolicyRespectLocalModeEl.checked = true;
        if (powerPolicyMaintenanceModeEl) powerPolicyMaintenanceModeEl.checked = false;
        if (powerPolicyStartFailureModeEl) powerPolicyStartFailureModeEl.value = 'fail_reservation_start';
        if (powerPolicyEndFailureModeEl) powerPolicyEndFailureModeEl.value = 'warn_and_continue';
        powerPolicyStepDrafts = [];
        renderPowerPolicySteps();
        if (powerPolicyEditorHintEl) powerPolicyEditorHintEl.textContent = 'Select a laboratory and configure the policy fields.';
    }

    function createPowerPolicyStepDraft(step = {}) {
        const action = String(step.action || 'on').trim().toLowerCase();
        const conditions = step.conditions && typeof step.conditions === 'object' && !Array.isArray(step.conditions)
            ? step.conditions
            : {};
        const parsedSequence = Number.parseInt(step.sequence, 10);
        const readInteger = (value, fallback) => {
            const parsed = Number.parseInt(value, 10);
            return Number.isInteger(parsed) ? parsed : fallback;
        };
        return {
            id: String(step.id || step.stepId || '').trim(),
            phase: String(step.phase || 'pre_start').trim().toLowerCase(),
            sequence: Number.isInteger(parsedSequence) && parsedSequence >= 0 ? parsedSequence : 10,
            controllerId: String(step.controllerId || step.controller_id || '').trim(),
            outlet: String(step.outlet || step.outletKey || step.outlet_key || '').trim(),
            logicalName: String(step.logicalName || step.logical_name || '').trim(),
            action: ['on', 'off', 'cycle'].includes(action) ? action : 'on',
            desiredState: step.desiredState || step.desired_state || (action === 'on' || action === 'off' ? action : ''),
            required: step.required !== false,
            readBackRequired: step.readBackRequired !== false && step.read_back_required !== false,
            offSeconds: readInteger(step.offSeconds ?? step.off_seconds, 10),
            delayBeforeSeconds: readInteger(step.delayBeforeSeconds ?? step.delay_before_seconds, 0),
            delayAfterSeconds: readInteger(step.delayAfterSeconds ?? step.delay_after_seconds, 0),
            timeoutSeconds: readInteger(step.timeoutSeconds ?? step.timeout_seconds, 20),
            retryCount: readInteger(step.retryCount ?? step.retry_count, 0),
            allowProtected: step.allowProtected === true || step.allow_protected === true,
            conditionsText: JSON.stringify(conditions, null, 2),
        };
    }

    function populatePowerPolicyForm(policy) {
        if (powerPolicyNameEl) powerPolicyNameEl.value = policy.policyName || '';
        if (powerPolicyEnabledEl) powerPolicyEnabledEl.checked = policy.enabled !== false;
        if (powerPolicyRespectLocalModeEl) powerPolicyRespectLocalModeEl.checked = policy.respectLocalMode !== false;
        if (powerPolicyMaintenanceModeEl) powerPolicyMaintenanceModeEl.checked = policy.maintenanceMode === true;
        if (powerPolicyStartFailureModeEl) powerPolicyStartFailureModeEl.value = policy.startFailureMode || 'fail_reservation_start';
        if (powerPolicyEndFailureModeEl) powerPolicyEndFailureModeEl.value = policy.endFailureMode || 'warn_and_continue';
        powerPolicyStepDrafts = Array.isArray(policy.steps)
            ? policy.steps.map(createPowerPolicyStepDraft)
            : [];
        renderPowerPolicySteps();
    }

    function powerPolicyControllerOptions(selectedId) {
        const options = powerControllers.map(controller => {
            const controllerId = String(controller.id || '').trim();
            const label = controller.name || controllerId;
            return `<option value="${escapeHtml(controllerId)}"${controllerId === selectedId ? ' selected' : ''}>${escapeHtml(label)}</option>`;
        }).join('');
        return `<option value="">Select controller</option>${options}`;
    }

    function getPowerControllerOutlets(controllerId) {
        const controller = powerControllers.find(item => String(item.id || '') === String(controllerId || ''));
        return Array.isArray(controller?.outlets) ? controller.outlets : [];
    }

    function powerPolicyOutletOptions(step) {
        const outlets = getPowerControllerOutlets(step.controllerId);
        const options = outlets.map(outlet => {
            const outletId = String(outlet.outlet || '').trim();
            const label = outlet.displayName || outlet.logicalName || outletId;
            return `<option value="${escapeHtml(outletId)}"${outletId === step.outlet ? ' selected' : ''}>${escapeHtml(label)} (${escapeHtml(outletId)})</option>`;
        }).join('');
        return `<option value="">${outlets.length ? 'Select outlet' : 'No outlets available'}</option>${options}`;
    }

    function powerPolicySelectOptions(values, selected, labels = {}) {
        return values.map(value => `<option value="${value}"${value === selected ? ' selected' : ''}>${labels[value] || value}</option>`).join('');
    }

    function renderPowerPolicySteps() {
        if (!powerPolicyStepsEl) return;
        if (!powerPolicyStepDrafts.length) {
            powerPolicyStepsEl.innerHTML = '<div class="empty">No steps configured. Add a step to control an outlet during a reservation phase.</div>';
            return;
        }
        const phases = ['pre_start', 'start', 'post_start', 'pre_end', 'end', 'post_end', 'manual', 'maintenance', 'emergency_stop'];
        const phaseLabels = {
            pre_start: 'Before start',
            start: 'Start',
            post_start: 'After start',
            pre_end: 'Before end',
            end: 'End',
            post_end: 'After end',
            manual: 'Manual',
            maintenance: 'Maintenance',
            emergency_stop: 'Emergency stop',
        };
        powerPolicyStepsEl.innerHTML = powerPolicyStepDrafts.map((step, index) => `
            <div class="power-policy-step" data-step-index="${index}">
                <div class="power-policy-step-header">
                    <strong>Step ${index + 1}</strong>
                    <button class="mini-btn danger" type="button" data-step-action="remove">Remove</button>
                </div>
                <div class="form-grid power-policy-step-fields">
                    <label class="field">
                        <span>Phase</span>
                        <select data-step-field="phase">${powerPolicySelectOptions(phases, step.phase, phaseLabels)}</select>
                    </label>
                    <label class="field">
                        <span>Sequence</span>
                        <input type="number" min="0" max="1000000" data-step-field="sequence" value="${step.sequence}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Controller</span>
                        <select data-step-field="controllerId">${powerPolicyControllerOptions(step.controllerId)}</select>
                    </label>
                    <label class="field">
                        <span>Outlet</span>
                        <select data-step-field="outlet">${powerPolicyOutletOptions(step)}</select>
                    </label>
                    <label class="field">
                        <span>Action</span>
                        <select data-step-field="action">${powerPolicySelectOptions(['on', 'off', 'cycle'], step.action)}</select>
                    </label>
                    <label class="field">
                        <span>Desired state</span>
                        <select data-step-field="desiredState">${powerPolicySelectOptions(['', 'on', 'off', 'unknown'], step.desiredState, { '': 'Use action default' })}</select>
                    </label>
                    <label class="field">
                        <span>Logical name</span>
                        <input type="text" maxlength="160" data-step-field="logicalName" value="${escapeHtml(step.logicalName)}" placeholder="Optional label">
                    </label>
                    <label class="field">
                        <span>Cycle off time (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="offSeconds" value="${step.offSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Delay before (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="delayBeforeSeconds" value="${step.delayBeforeSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Delay after (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="delayAfterSeconds" value="${step.delayAfterSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Timeout (seconds)</span>
                        <input type="number" min="0" max="300" data-step-field="timeoutSeconds" value="${step.timeoutSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Retries</span>
                        <input type="number" min="0" max="5" data-step-field="retryCount" value="${step.retryCount}" inputmode="numeric">
                    </label>
                </div>
                <div class="power-policy-step-options">
                    <label class="check-field"><input type="checkbox" data-step-field="required"${step.required ? ' checked' : ''}> Required</label>
                    <label class="check-field"><input type="checkbox" data-step-field="readBackRequired"${step.readBackRequired ? ' checked' : ''}> Read back state</label>
                    <label class="check-field"><input type="checkbox" data-step-field="allowProtected"${step.allowProtected ? ' checked' : ''}> Allow protected outlet</label>
                </div>
                <label class="field power-policy-conditions">
                    <span>Conditions (advanced JSON, optional)</span>
                    <textarea rows="3" data-step-field="conditions" spellcheck="false">${escapeHtml(step.conditionsText)}</textarea>
                </label>
            </div>
        `).join('');
    }

    function getPowerPolicyStepIndex(target) {
        const row = target?.closest?.('[data-step-index]');
        const index = Number.parseInt(row?.dataset?.stepIndex, 10);
        return Number.isInteger(index) && index >= 0 && index < powerPolicyStepDrafts.length ? index : -1;
    }

    function handlePowerPolicyStepChange(event) {
        const field = event.target?.dataset?.stepField;
        if (!field) return;
        const index = getPowerPolicyStepIndex(event.target);
        if (index < 0) return;
        const step = powerPolicyStepDrafts[index];
        step[field] = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
        if (field === 'controllerId') {
            step.outlet = '';
            renderPowerPolicySteps();
        } else if (field === 'action') {
            if (event.target.value === 'on' || event.target.value === 'off') step.desiredState = event.target.value;
            renderPowerPolicySteps();
        }
    }

    function handlePowerPolicyStepActions(event) {
        const button = event.target?.closest?.('[data-step-action]');
        if (!button || button.dataset.stepAction !== 'remove') return;
        const index = getPowerPolicyStepIndex(button);
        if (index < 0) return;
        powerPolicyStepDrafts.splice(index, 1);
        renderPowerPolicySteps();
    }

    function addPowerPolicyStep() {
        const phase = 'pre_start';
        const phaseSequences = powerPolicyStepDrafts
            .filter(step => step.phase === phase)
            .map(step => Number(step.sequence) || 0);
        const firstController = powerControllers[0];
        const firstOutlet = Array.isArray(firstController?.outlets) ? firstController.outlets[0] : null;
        powerPolicyStepDrafts.push(createPowerPolicyStepDraft({
            phase,
            sequence: (phaseSequences.length ? Math.max(...phaseSequences) : 0) + 10,
            controllerId: firstController?.id || '',
            outlet: firstOutlet?.outlet || '',
        }));
        renderPowerPolicySteps();
    }

    function parsePowerPolicyInteger(value, fieldName, maximum) {
        const parsed = Number.parseInt(value, 10);
        if (!Number.isInteger(parsed) || parsed < 0 || parsed > maximum) {
            throw new Error(`${fieldName} must be between 0 and ${maximum}`);
        }
        return parsed;
    }

    function readPowerPolicyForm() {
        const policyName = (powerPolicyNameEl?.value || '').trim();
        if (!policyName) throw new Error('Policy name is required');
        const steps = powerPolicyStepDrafts.map((step, index) => {
            if (!step.phase) throw new Error(`Step ${index + 1}: phase is required`);
            if (!step.controllerId) throw new Error(`Step ${index + 1}: select a controller`);
            if (!step.outlet) throw new Error(`Step ${index + 1}: select an outlet`);
            if (!['pre_start', 'start', 'post_start', 'pre_end', 'end', 'post_end', 'manual', 'maintenance', 'emergency_stop'].includes(step.phase)) {
                throw new Error(`Step ${index + 1}: unsupported phase`);
            }
            if (!['on', 'off', 'cycle'].includes(step.action)) {
                throw new Error(`Step ${index + 1}: unsupported action`);
            }
            if (step.desiredState && !['on', 'off', 'unknown'].includes(step.desiredState)) {
                throw new Error(`Step ${index + 1}: unsupported desired state`);
            }
            let conditions = {};
            if (step.conditionsText?.trim()) {
                try {
                    conditions = JSON.parse(step.conditionsText);
                } catch (err) {
                    throw new Error(`Step ${index + 1}: conditions JSON is invalid`);
                }
                if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) {
                    throw new Error(`Step ${index + 1}: conditions must be an object`);
                }
            }
            const offSeconds = parsePowerPolicyInteger(step.offSeconds, 'Cycle off time', 3600);
            if (step.action === 'cycle' && offSeconds === 0) {
                throw new Error(`Step ${index + 1}: cycle off time must be greater than zero`);
            }
            const normalized = {
                phase: step.phase,
                sequence: parsePowerPolicyInteger(step.sequence, 'Sequence', 1000000),
                controllerId: step.controllerId,
                outlet: step.outlet,
                action: step.action,
                required: step.required === true,
                readBackRequired: step.readBackRequired === true,
                offSeconds,
                delayBeforeSeconds: parsePowerPolicyInteger(step.delayBeforeSeconds, 'Delay before', 3600),
                delayAfterSeconds: parsePowerPolicyInteger(step.delayAfterSeconds, 'Delay after', 3600),
                timeoutSeconds: parsePowerPolicyInteger(step.timeoutSeconds, 'Timeout', 300),
                retryCount: parsePowerPolicyInteger(step.retryCount, 'Retries', 5),
                allowProtected: step.allowProtected === true,
                conditions,
            };
            if (step.id) normalized.id = step.id;
            if (step.logicalName) normalized.logicalName = step.logicalName;
            if (step.desiredState) normalized.desiredState = step.desiredState;
            return normalized;
        });
        return {
            policyName,
            enabled: powerPolicyEnabledEl?.checked !== false,
            respectLocalMode: powerPolicyRespectLocalModeEl?.checked !== false,
            maintenanceMode: powerPolicyMaintenanceModeEl?.checked === true,
            startFailureMode: powerPolicyStartFailureModeEl?.value || 'fail_reservation_start',
            endFailureMode: powerPolicyEndFailureModeEl?.value || 'warn_and_continue',
            steps,
        };
    }

    async function savePowerPolicy() {
        const labId = powerPolicyLabSelectEl?.value || '';
        if (!labId) {
            showToast('Select a laboratory before saving the policy', 'error');
            return;
        }
        let policy;
        try {
            policy = readPowerPolicyForm();
        } catch (err) {
            showToast(`Power policy is invalid: ${err.message}`, 'error');
            return;
        }
        policy.labId = labId;
        delete policy.lab_id;
        if (savePowerPolicyBtn) savePowerPolicyBtn.disabled = true;
        try {
            const res = await fetch(`/ops/api/power/policies/${encodeURIComponent(labId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(policy)
            });
            const body = await res.json().catch(() => ({}));
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) throw new Error('Lab Manager session required');
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            showToast(`Power policy for ${labId} saved`, 'success');
            await loadPowerPolicies({ skipAuthPrompt: true });
            if (powerPolicySelectEl) powerPolicySelectEl.value = labId;
            loadSelectedPowerPolicy();
        } catch (err) {
            showToast(`Power policy save failed: ${err.message}`, 'error');
        } finally {
            if (savePowerPolicyBtn) savePowerPolicyBtn.disabled = false;
        }
    }

    function createPowerControllerOutletDraft(outlet = {}) {
        return {
            outlet: String(outlet.outlet || outlet.outletKey || '').trim(),
            displayName: String(outlet.displayName || '').trim(),
            logicalName: String(outlet.logicalName || '').trim(),
            protected: outlet.protected === true,
            critical: outlet.critical === true,
            defaultState: outlet.defaultState === 'on' ? 'on' : 'off',
        };
    }

    function updatePowerControllerDriverFields() {
        const driver = powerControllerDriverEl?.value || 'mock';
        const isNetio = driver === 'netio-json';
        const isApc = driver === 'apc-powernet-snmp';
        const currentPort = String(powerControllerPortEl?.value || '');
        if (powerControllerPortEl && driver === 'netio-json' && lastPowerControllerDriver !== 'netio-json' && currentPort === '161') {
            powerControllerPortEl.value = powerControllerNetioHttpsEl?.checked === true ? '443' : '80';
        } else if (powerControllerPortEl && driver !== 'netio-json' && lastPowerControllerDriver === 'netio-json' && ['80', '443'].includes(currentPort)) {
            powerControllerPortEl.value = '161';
        }
        lastPowerControllerDriver = driver;
        if (powerControllerNetioPathFieldEl) powerControllerNetioPathFieldEl.hidden = !isNetio;
        if (powerControllerNetioHttpsFieldEl) powerControllerNetioHttpsFieldEl.hidden = !isNetio;
        if (powerControllerNetioVerifyTlsFieldEl) powerControllerNetioVerifyTlsFieldEl.hidden = !isNetio;
        if (powerControllerProfileFieldEl) powerControllerProfileFieldEl.hidden = !isApc;
        if (powerControllerSnmpVersionFieldEl) powerControllerSnmpVersionFieldEl.hidden = !isApc;
    }

    function updatePowerControllerNetioPort() {
        if (powerControllerDriverEl?.value !== 'netio-json' || !powerControllerPortEl) return;
        if (['80', '443'].includes(String(powerControllerPortEl.value || ''))) {
            powerControllerPortEl.value = powerControllerNetioHttpsEl?.checked === true ? '443' : '80';
        }
    }

    function resetPowerControllerEditor() {
        if (powerControllerSelectEl) powerControllerSelectEl.value = '';
        if (powerControllerIdEl) {
            powerControllerIdEl.value = '';
            powerControllerIdEl.disabled = false;
        }
        if (powerControllerNameEl) powerControllerNameEl.value = '';
        if (powerControllerDriverEl) powerControllerDriverEl.value = 'mock';
        if (powerControllerEnabledEl) powerControllerEnabledEl.checked = true;
        if (powerControllerHostEl) powerControllerHostEl.value = '';
        if (powerControllerPortEl) powerControllerPortEl.value = '161';
        if (powerControllerCredentialRefEl) powerControllerCredentialRefEl.value = '';
        if (powerControllerNetioPathEl) powerControllerNetioPathEl.value = '/netio.json';
        if (powerControllerNetioHttpsEl) powerControllerNetioHttpsEl.checked = false;
        if (powerControllerNetioVerifyTlsEl) powerControllerNetioVerifyTlsEl.checked = true;
        if (powerControllerProfileEl) powerControllerProfileEl.value = 'auto';
        if (powerControllerSnmpVersionEl) powerControllerSnmpVersionEl.value = '';
        if (powerControllerTimeoutSecondsEl) powerControllerTimeoutSecondsEl.value = '2';
        if (powerControllerRetriesEl) powerControllerRetriesEl.value = '1';
        updatePowerControllerDriverFields();
        powerControllerOutletDrafts = [createPowerControllerOutletDraft({ outlet: '1' })];
        renderPowerControllerOutlets();
        if (powerControllerEditorHintEl) powerControllerEditorHintEl.textContent = 'Select an existing controller or configure a new one.';
    }

    function populatePowerControllerForm(controller) {
        if (powerControllerIdEl) {
            powerControllerIdEl.value = controller.id || '';
            powerControllerIdEl.disabled = true;
        }
        if (powerControllerNameEl) powerControllerNameEl.value = controller.name || '';
        if (powerControllerDriverEl) powerControllerDriverEl.value = controller.driver || 'mock';
        if (powerControllerEnabledEl) powerControllerEnabledEl.checked = controller.enabled !== false;
        if (powerControllerHostEl) powerControllerHostEl.value = controller.host || '';
        if (powerControllerCredentialRefEl) powerControllerCredentialRefEl.value = controller.credentialRef || '';
        const config = controller.config || {};
        const defaultPort = controller.driver === 'netio-json'
            ? (config.useHttps === true ? '443' : '80')
            : '161';
        if (powerControllerPortEl) powerControllerPortEl.value = controller.port || defaultPort;
        if (powerControllerNetioPathEl) powerControllerNetioPathEl.value = config.path || '/netio.json';
        if (powerControllerNetioHttpsEl) powerControllerNetioHttpsEl.checked = config.useHttps === true;
        if (powerControllerNetioVerifyTlsEl) powerControllerNetioVerifyTlsEl.checked = config.verifyTls !== false;
        if (powerControllerProfileEl) powerControllerProfileEl.value = config.profile || 'auto';
        if (powerControllerSnmpVersionEl) powerControllerSnmpVersionEl.value = config.snmpVersion || '';
        if (powerControllerTimeoutSecondsEl) powerControllerTimeoutSecondsEl.value = config.timeoutSeconds || '2';
        if (powerControllerRetriesEl) powerControllerRetriesEl.value = config.retries ?? '1';
        updatePowerControllerDriverFields();
        powerControllerOutletDrafts = Array.isArray(controller.outlets)
            ? controller.outlets.map(createPowerControllerOutletDraft)
            : [];
        renderPowerControllerOutlets();
        if (powerControllerEditorHintEl) powerControllerEditorHintEl.textContent = 'Edit the provider-local controller and save it to apply the configuration.';
    }

    function renderPowerControllerOptions() {
        if (!powerControllerSelectEl) return;
        const current = powerControllerSelectEl.value;
        powerControllerSelectEl.innerHTML = '<option value="">New controller</option>';
        powerControllers.forEach(controller => {
            const option = document.createElement('option');
            option.value = controller.id || '';
            option.textContent = `${controller.id || 'unknown'} Â· ${controller.name || 'Unnamed controller'}`;
            powerControllerSelectEl.appendChild(option);
        });
        const selected = powerControllers.some(controller => String(controller.id) === String(current)) ? current : '';
        powerControllerSelectEl.value = selected;
        if (selected) {
            loadSelectedPowerController();
        } else {
            resetPowerControllerEditor();
        }
    }

    function loadSelectedPowerController() {
        const controllerId = powerControllerSelectEl?.value || '';
        const controller = powerControllers.find(item => String(item.id || '') === String(controllerId));
        if (controller) {
            populatePowerControllerForm(controller);
            return;
        }
        resetPowerControllerEditor();
    }

    function renderPowerControllerOutlets() {
        if (!powerControllerOutletsEl) return;
        if (!powerControllerOutletDrafts.length) {
            powerControllerOutletsEl.innerHTML = '<div class="empty">No outlets configured. Add at least one outlet before saving.</div>';
            return;
        }
        powerControllerOutletsEl.innerHTML = powerControllerOutletDrafts.map((outlet, index) => `
            <div class="power-controller-outlet-config" data-controller-outlet-index="${index}">
                <div class="power-controller-outlet-config-header">
                    <strong>Outlet ${index + 1}</strong>
                    <button class="mini-btn danger" type="button" data-controller-outlet-action="remove">Remove</button>
                </div>
                <div class="form-grid power-controller-outlet-fields">
                    <label class="field">
                        <span>Outlet ID</span>
                        <input type="text" maxlength="64" data-controller-outlet-field="outlet" value="${escapeHtml(outlet.outlet)}" placeholder="1">
                    </label>
                    <label class="field">
                        <span>Display name</span>
                        <input type="text" maxlength="160" data-controller-outlet-field="displayName" value="${escapeHtml(outlet.displayName)}" placeholder="PLC power">
                    </label>
                    <label class="field">
                        <span>Logical name</span>
                        <input type="text" maxlength="160" data-controller-outlet-field="logicalName" value="${escapeHtml(outlet.logicalName)}" placeholder="plc">
                    </label>
                    <label class="field">
                        <span>Default state</span>
                        <select data-controller-outlet-field="defaultState">
                            <option value="off"${outlet.defaultState === 'off' ? ' selected' : ''}>Off</option>
                            <option value="on"${outlet.defaultState === 'on' ? ' selected' : ''}>On</option>
                        </select>
                    </label>
                </div>
                <div class="power-controller-outlet-options">
                    <label class="check-field"><input type="checkbox" data-controller-outlet-field="protected"${outlet.protected ? ' checked' : ''}> Protected</label>
                    <label class="check-field"><input type="checkbox" data-controller-outlet-field="critical"${outlet.critical ? ' checked' : ''}> Critical</label>
                </div>
            </div>
        `).join('');
    }

    function getPowerControllerOutletIndex(target) {
        const row = target?.closest?.('[data-controller-outlet-index]');
        const index = Number.parseInt(row?.dataset?.controllerOutletIndex, 10);
        return Number.isInteger(index) && index >= 0 && index < powerControllerOutletDrafts.length ? index : -1;
    }

    function handlePowerControllerOutletChange(event) {
        const field = event.target?.dataset?.controllerOutletField;
        if (!field) return;
        const index = getPowerControllerOutletIndex(event.target);
        if (index < 0) return;
        powerControllerOutletDrafts[index][field] = event.target.type === 'checkbox'
            ? event.target.checked
            : event.target.value;
    }

    function handlePowerControllerOutletActions(event) {
        const button = event.target?.closest?.('[data-controller-outlet-action]');
        if (!button || button.dataset.controllerOutletAction !== 'remove') return;
        const index = getPowerControllerOutletIndex(button);
        if (index < 0) return;
        powerControllerOutletDrafts.splice(index, 1);
        renderPowerControllerOutlets();
    }

    function addPowerControllerOutlet() {
        const usedIds = new Set(powerControllerOutletDrafts.map(outlet => outlet.outlet));
        let nextId = 1;
        while (usedIds.has(String(nextId))) nextId += 1;
        powerControllerOutletDrafts.push(createPowerControllerOutletDraft({ outlet: String(nextId) }));
        renderPowerControllerOutlets();
    }

    function readPowerControllerForm() {
        const id = (powerControllerIdEl?.value || '').trim();
        const name = (powerControllerNameEl?.value || '').trim();
        const driver = (powerControllerDriverEl?.value || '').trim();
        if (!id) throw new Error('Controller ID is required');
        if (!/^[A-Za-z0-9._:-]+$/.test(id)) throw new Error('Controller ID contains invalid characters');
        if (!name) throw new Error('Controller name is required');
        if (!['mock', 'apc-powernet-snmp', 'netio-json'].includes(driver)) throw new Error('Select a supported driver');
        const useHttps = powerControllerNetioHttpsEl?.checked === true;
        const defaultPort = driver === 'netio-json' ? (useHttps ? 443 : 80) : 161;
        const port = Number.parseInt(powerControllerPortEl?.value || String(defaultPort), 10);
        if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Port must be between 1 and 65535');
        const timeoutSeconds = Number.parseInt(powerControllerTimeoutSecondsEl?.value || '2', 10);
        if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 60) throw new Error('Timeout must be between 1 and 60 seconds');
        const retries = Number.parseInt(powerControllerRetriesEl?.value || '1', 10);
        if (!Number.isInteger(retries) || retries < 1 || retries > 10) throw new Error('Retries must be between 1 and 10');
        const host = (powerControllerHostEl?.value || '').trim();
        const credentialRef = (powerControllerCredentialRefEl?.value || '').trim();
        if (driver !== 'mock' && !host) throw new Error('Host is required for this driver');
        if (driver === 'apc-powernet-snmp' && !credentialRef) throw new Error('Credential reference is required for APC SNMP');

        const outlets = powerControllerOutletDrafts.map((outlet, index) => {
            const outletId = String(outlet.outlet || '').trim();
            if (!outletId) throw new Error(`Outlet ${index + 1}: ID is required`);
            return {
                outlet: outletId,
                displayName: outlet.displayName || '',
                logicalName: outlet.logicalName || '',
                protected: outlet.protected === true,
                critical: outlet.critical === true,
                defaultState: outlet.defaultState === 'on' ? 'on' : 'off',
            };
        });
        if (!outlets.length) throw new Error('At least one outlet is required');
        if (new Set(outlets.map(outlet => outlet.outlet)).size !== outlets.length) throw new Error('Outlet IDs must be unique');

        const config = driver === 'netio-json'
            ? {
                path: (powerControllerNetioPathEl?.value || '/netio.json').trim(),
                useHttps,
                verifyTls: powerControllerNetioVerifyTlsEl?.checked !== false,
                timeoutSeconds,
                retries,
            }
            : {
                profile: powerControllerProfileEl?.value || 'auto',
                snmpVersion: powerControllerSnmpVersionEl?.value || undefined,
                timeoutSeconds,
                retries,
            };
        if (driver === 'netio-json' && (!config.path || !config.path.startsWith('/') || config.path.includes('\n') || config.path.includes('\r'))) {
            throw new Error('NETIO API path must start with /');
        }
        if (!config.snmpVersion) delete config.snmpVersion;
        return {
            id,
            name,
            driver,
            enabled: powerControllerEnabledEl?.checked !== false,
            host,
            port,
            credentialRef,
            config,
            outlets,
        };
    }

    async function savePowerController() {
        let controller;
        try {
            controller = readPowerControllerForm();
        } catch (err) {
            showToast(`Power controller is invalid: ${err.message}`, 'error');
            return;
        }
        const existingId = powerControllerSelectEl?.value || '';
        const method = existingId ? 'PUT' : 'POST';
        const url = existingId
            ? `/ops/api/power/controllers/${encodeURIComponent(existingId)}`
            : '/ops/api/power/controllers';
        if (savePowerControllerBtn) savePowerControllerBtn.disabled = true;
        try {
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(controller),
            });
            const body = await res.json().catch(() => ({}));
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) throw new Error('Lab Manager session required');
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            showToast(`Power controller ${controller.id} saved`, 'success');
            await loadPowerControllers({ skipAuthPrompt: true });
            if (powerControllerSelectEl) powerControllerSelectEl.value = controller.id;
            loadSelectedPowerController();
        } catch (err) {
            showToast(`Power controller save failed: ${err.message}`, 'error');
        } finally {
            if (savePowerControllerBtn) savePowerControllerBtn.disabled = false;
        }
    }

    function renderPowerControllers() {
        if (!powerControllerListEl) return;
        powerControllerListEl.innerHTML = '';
        if (!powerControllers.length) {
            powerControllerListEl.innerHTML = '<div class="empty">No power controllers are configured.</div>';
            return;
        }
        powerControllers.forEach(controller => {
            const row = document.createElement('div');
            row.className = 'power-controller-row';
            const discovery = controller.discovery || {};
            const reachable = discovery.reachable === true;
            const discoveryText = reachable
                ? 'reachable'
                : discovery.errorCode ? `unreachable (${discovery.errorCode})` : 'unknown reachability';
            const safeControllerId = escapeHtml(controller.id);
            const safeName = escapeHtml(controller.name || controller.id);
            const safeDriver = escapeHtml(controller.driver);
            const safeHost = escapeHtml(controller.host || 'local/mock');
            const safeDiscovery = escapeHtml(discoveryText);
            const outlets = Array.isArray(controller.outlets) ? controller.outlets : [];
            row.innerHTML = `
                <div class="power-controller-heading">
                    <div>
                        <div class="host-title">${safeName}</div>
                        <div class="host-meta mono">${safeControllerId} · ${safeDriver} · ${safeHost}</div>
                    </div>
                    <span class="pill ${reachable ? 'good' : 'warn'}">${safeDiscovery}</span>
                </div>
                <div class="power-outlet-list">
                    ${outlets.length ? outlets.map(outlet => renderPowerOutlet(controller, outlet)).join('') : '<div class="empty">No outlets configured.</div>'}
                </div>
            `;
            powerControllerListEl.appendChild(row);
        });
    }

    function renderPowerOutlet(controller, outlet) {
        const protectedOutlet = outlet.protected === true;
        const state = String(outlet.state || 'unknown').toLowerCase();
        const stateClass = state === 'on' ? 'good' : state === 'off' ? 'soft' : 'warn';
        const label = outlet.displayName || outlet.logicalName || outlet.outlet;
        return `
            <div class="power-outlet-row">
                <div>
                    <div class="item-title">${escapeHtml(label)}</div>
                    <div class="host-meta">Outlet ${escapeHtml(outlet.outlet)}${protectedOutlet ? ' · protected' : ''}${outlet.critical ? ' · critical' : ''}</div>
                </div>
                <div class="power-outlet-actions">
                    <span class="pill ${stateClass}">${escapeHtml(state)}</span>
                    <button class="mini-btn" data-power-action="on" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">On</button>
                    <button class="mini-btn" data-power-action="off" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">Off</button>
                    <button class="mini-btn primary" data-power-action="cycle" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">Cycle</button>
                </div>
            </div>
        `;
    }

    async function handlePowerActions(event) {
        const button = event.target.closest('[data-power-action]');
        if (!button) return;
        const action = button.dataset.powerAction;
        const controllerId = button.dataset.controllerId;
        const outletId = button.dataset.outletId;
        const protectedOutlet = button.dataset.protected === 'true';
        if (protectedOutlet && !powerMaintenanceModeEl?.checked) {
            showToast('Enable maintenance mode before operating a protected outlet', 'error');
            return;
        }
        const offSeconds = Number.parseInt(powerCycleSecondsEl?.value || '10', 10);
        if (action === 'cycle' && (!Number.isInteger(offSeconds) || offSeconds < 1 || offSeconds > 3600)) {
            showToast('Cycle off time must be between 1 and 3600 seconds', 'error');
            return;
        }
        button.disabled = true;
        try {
            const payload = {
                command: action === 'cycle' ? 'cycle' : 'set_state',
                state: action === 'cycle' ? undefined : action,
                actor: 'lab-manager',
                reason: powerOperationReasonEl?.value.trim() || 'Lab Manager manual power test',
                idempotencyKey: createPowerIdempotencyKey(),
                offSeconds: action === 'cycle' ? offSeconds : undefined,
                allowProtected: protectedOutlet,
                maintenance: protectedOutlet && Boolean(powerMaintenanceModeEl?.checked)
            };
            Object.keys(payload).forEach(key => payload[key] === undefined && delete payload[key]);
            const res = await fetch(
                `/ops/api/power/controllers/${encodeURIComponent(controllerId)}/outlets/${encodeURIComponent(outletId)}/commands`,
                { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }
            );
            const body = await res.json().catch(() => ({}));
            if (res.status === 403) {
                showOpsWarning();
                return;
            }
            if (res.status === 401) throw new Error('Lab Manager session required');
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            showToast(`Power ${action} completed for outlet ${outletId}`, 'success');
            await loadPowerControllers({ skipAuthPrompt: true });
        } catch (err) {
            showToast(`Power ${action} failed: ${err.message}`, 'error');
        } finally {
            button.disabled = false;
        }
    }

    function createPowerIdempotencyKey() {
        if (window.crypto?.randomUUID) return `lab-manager:${window.crypto.randomUUID()}`;
        return `lab-manager:${Date.now()}:${Math.random().toString(36).slice(2)}`;
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
        if (provisionHostLabsSummaryEl) {
            provisionHostLabsSummaryEl.hidden = true;
            provisionHostLabsSummaryEl.textContent = '';
        }
        provisionHostLabsEl.hidden = false;
        const selectedSet = new Set(selectedIds.map(String));
        const validLabs = (Array.isArray(labs) ? labs : [])
            .filter(lab => String(lab?.labId || '').trim());
        if (!validLabs.length) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No matching labs found';
            option.disabled = true;
            provisionHostLabsEl.appendChild(option);
            provisionHostLabsEl.disabled = true;
            return;
        }
        provisionHostLabsEl.disabled = false;
        const singleLab = validLabs.length === 1;
        validLabs.forEach(lab => {
            const labId = String(lab.labId || '').trim();
            const option = document.createElement('option');
            option.value = labId;
            option.textContent = formatProvisionLabLabel(lab);
            option.selected = singleLab || selectedSet.has(labId);
            provisionHostLabsEl.appendChild(option);
        });
        if (singleLab && provisionHostLabsSummaryEl) {
            provisionHostLabsSummaryEl.textContent = formatProvisionLabLabel(validLabs[0]);
            provisionHostLabsSummaryEl.hidden = false;
            provisionHostLabsEl.hidden = true;
        }
    }

    function formatProvisionLabLabel(lab) {
        const labId = String(lab?.labId || '').trim();
        return `Lab ${labId}${lab?.accessKey ? ` - ${lab.accessKey}` : ''}`;
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
        const host = candidate.name || candidate.hostname || '';
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

    async function loadActivityFeed(append = false, options = {}) {
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
            const res = await fetch(`/ops/api/operations/recent?${params.toString()}`, {
                credentials: 'include',
                ...options,
            });
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

    async function loadActionableReservations({ append = false } = {}) {
        if (!upcomingReservationsListEl) return;
        if (actionableReservationsState.loading) return;
        if (!append) {
            actionableReservationsState.reservations = [];
            actionableReservationsState.offset = 0;
            actionableReservationsState.nextOffset = 0;
            actionableReservationsState.cursor = null;
            actionableReservationsState.total = null;
            actionableReservationsState.totalKnown = false;
            actionableReservationsState.hasMore = false;
        }
        actionableReservationsState.loading = true;
        setUpcomingReservationsStatus(append ? 'Loading more...' : 'Loading...', 'soft');
        try {
            const params = new URLSearchParams({
                limit: String(ACTIONABLE_RESERVATIONS_PAGE_SIZE),
                offset: String(actionableReservationsState.nextOffset)
            });
            if (actionableReservationsState.cursor) {
                params.set('cursor', actionableReservationsState.cursor);
            }
            const res = await fetch(`/lab-admin/reservations/actionable?${params.toString()}`, { credentials: 'include' });
            if (res.status === 401) {
                renderUpcomingReservationsMessage('Unauthorized: check LAB_MANAGER_TOKEN.');
                setUpcomingReservationsStatus('Unauthorized', 'bad');
                return;
            }
            if (res.status === 403) {
                renderUpcomingReservationsMessage('Access denied: provider reservation administration is not available.');
                setUpcomingReservationsStatus('Access denied', 'bad');
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(body.error || `Unable to load reservations (HTTP ${res.status}).`);
            }
            const page = Array.isArray(body.reservations) ? body.reservations : [];
            const pagination = body.pagination || {};
            const returned = Number.isFinite(Number(pagination.returned))
                ? Number(pagination.returned)
                : page.length;
            const nextOffset = Number.isFinite(Number(pagination.nextOffset))
                ? Number(pagination.nextOffset)
                : Number.isFinite(Number(body.nextOffset))
                    ? Number(body.nextOffset)
                    : actionableReservationsState.nextOffset + returned;
            actionableReservationsState.reservations = append
                ? actionableReservationsState.reservations.concat(page)
                : page;
            actionableReservationsState.offset = Number.isFinite(Number(pagination.offset))
                ? Number(pagination.offset)
                : Number.isFinite(Number(body.offset))
                    ? Number(body.offset)
                    : actionableReservationsState.offset;
            actionableReservationsState.nextOffset = nextOffset;
            actionableReservationsState.cursor = typeof pagination.nextCursor === 'string'
                ? pagination.nextCursor
                : typeof body.nextCursor === 'string'
                    ? body.nextCursor
                    : null;
            const totalKnown = Number.isFinite(Number(pagination.total))
                || Number.isFinite(Number(body.totalCount));
            actionableReservationsState.totalKnown = totalKnown;
            actionableReservationsState.total = totalKnown
                ? Number.isFinite(Number(pagination.total))
                    ? Number(pagination.total)
                    : Number(body.totalCount)
                : null;
            actionableReservationsState.hasMore = typeof pagination.hasMore === 'boolean'
                ? pagination.hasMore
                : typeof body.hasMore === 'boolean'
                    ? body.hasMore
                    : Boolean(body.truncated);
            renderUpcomingReservations();
            const loadedCount = actionableReservationsState.reservations.length;
            const totalCount = actionableReservationsState.totalKnown
                ? actionableReservationsState.total
                : loadedCount;
            const status = actionableReservationsState.hasMore
                ? actionableReservationsState.totalKnown
                    ? `${loadedCount} of ${totalCount} actionable`
                    : `${loadedCount}+ actionable`
                : `${totalCount} actionable`;
            setUpcomingReservationsStatus(status, 'soft');
        } catch (err) {
            console.error(err);
            if (!append) renderUpcomingReservationsMessage('Unable to load actionable reservations.');
            setUpcomingReservationsStatus('Unavailable', 'bad');
        } finally {
            actionableReservationsState.loading = false;
        }
    }

    function renderUpcomingReservations() {
        if (!upcomingReservationsListEl) return;
        const reservations = actionableReservationsState.reservations;
        if (!reservations.length) {
            renderUpcomingReservationsMessage('No actionable reservations for your labs.');
            return;
        }

        const items = reservations.map(reservation => {
            const key = String(reservation.reservationKey || '');
            const status = String(reservation.statusLabel || 'UNKNOWN');
            const numericStatus = normalizeReservationStatus(reservation.status);
            const statusClass = numericStatus === 1 ? 'good' : numericStatus === 0 ? 'warn' : 'soft';
            const reasonOptions = Array.isArray(reservation.cancellationOptions)
                ? reservation.cancellationOptions
                    .map(option => ({
                        code: Number(option.reasonCode),
                        label: String(option.label || `Reason ${option.reasonCode}`),
                        deadline: Number(option.deadline),
                        penalty: Number(option.reputationPenalty)
                    }))
                    .filter(option => Number.isInteger(option.code))
                : [];
            const actions = reservation.cancellable && reasonOptions.length
                ? `<div class="reservation-item-actions">
                    <select class="reservation-reason" aria-label="Cancellation reason" data-reservation-reason>
                        ${reasonOptions.map(option => {
                            const deadline = Number.isFinite(option.deadline)
                                ? `until ${formatReservationDate(option.deadline)}`
                                : 'deadline unavailable';
                            const penalty = Number.isFinite(option.penalty)
                                ? `${option.penalty} reputation`
                                : 'penalty unavailable';
                            return `<option value="${option.code}">Reason ${option.code}: ${escapeHtml(option.label)} · ${escapeHtml(penalty)} · ${escapeHtml(deadline)}</option>`;
                        }).join('')}
                    </select>
                    <button type="button" class="mini-btn danger" data-action="cancel-reservation" data-reservation-key="${escapeHtml(key)}">
                        ${cancellationButtonLabel(numericStatus)}
                    </button>
                </div>`
                : `<div class="reservation-cancel-note">Cancellation unavailable for this status.</div>`;
            const renter = shortAddress(reservation.renter);
            const labLabel = reservation.labName || `Lab #${reservation.labId}`;
            const institution = reservation.institutionName || shortAddress(reservation.institutionAddress);
            return `<article class="reservation-item" data-reservation-key="${escapeHtml(key)}" data-reservation-status="${numericStatus ?? ''}">
                <div class="reservation-item-heading">
                    <span class="item-title">${escapeHtml(labLabel)}</span>
                    <span class="reservation-item-reference">Reservation: <code title="${escapeHtml(key)}">${escapeHtml(shortAddress(key, 12, 10))}</code></span>
                    <span class="pill ${statusClass}">${escapeHtml(status)}</span>
                </div>
                <div class="reservation-item-schedule">
                    <span>${escapeHtml(formatReservationDate(reservation.start))} – ${escapeHtml(formatReservationDate(reservation.end))}</span>
                    ${actions}
                </div>
                <div class="reservation-item-meta">
                    <span>Price: ${escapeHtml(reservation.priceCredits || '0')} service credits</span>
                    <span>Provider share: ${escapeHtml(reservation.providerShareCredits || '0')} credits</span>
                    <span>Renter: (${escapeHtml(institution || 'Unknown')}) ${escapeHtml(renter)}</span>
                </div>
            </article>`;
        }).join('');
        const loadMore = actionableReservationsState.hasMore
            ? '<div class="reservation-pagination"><button type="button" class="mini-btn primary" data-action="load-more-actionable">Load more</button></div>'
            : '';
        upcomingReservationsListEl.innerHTML = `${items}${loadMore}`;
    }

    function renderUpcomingReservationsMessage(message) {
        if (upcomingReservationsListEl) {
            upcomingReservationsListEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
        }
    }

    function setUpcomingReservationsStatus(message, type) {
        if (!upcomingReservationsStatusEl) return;
        upcomingReservationsStatusEl.textContent = message;
        upcomingReservationsStatusEl.className = `pill ${type || 'soft'}`;
    }

    function formatReservationDate(epochSeconds) {
        const timestamp = Number(epochSeconds);
        if (!Number.isFinite(timestamp)) return 'Unknown time';
        return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
            .format(new Date(timestamp * 1000));
    }

    function normalizeReservationStatus(status) {
        const numericStatus = Number(status);
        return Number.isInteger(numericStatus) ? numericStatus : null;
    }

    function cancellationButtonLabel(status) {
        if (status === 0) return 'Decline request';
        if (status === 2) return 'Report service failure';
        return 'Cancel reservation';
    }

    function shortAddress(value, prefixLength = 6, suffixLength = 4) {
        const text = String(value || '');
        if (text.length <= prefixLength + suffixLength + 3) return text;
        return `${text.slice(0, prefixLength)}…${text.slice(-suffixLength)}`;
    }

    async function handleUpcomingReservationActions(event) {
        const loadMoreButton = event.target.closest('[data-action="load-more-actionable"]');
        if (loadMoreButton && upcomingReservationsListEl.contains(loadMoreButton)) {
            await loadActionableReservations({ append: true });
            return;
        }
        const button = event.target.closest('[data-action="cancel-reservation"]');
        if (!button || !upcomingReservationsListEl.contains(button)) return;
        const row = button.closest('.reservation-item');
        const key = row?.dataset.reservationKey;
        const reservationStatus = normalizeReservationStatus(row?.dataset.reservationStatus);
        const reasonEl = row?.querySelector('[data-reservation-reason]');
        const reasonCode = Number(reasonEl?.value);
        if (!key || !Number.isInteger(reasonCode)) return;
        const confirmationMessage = reservationStatus === 2
            ? 'Report provider service failure for this access-authorized reservation? The full price returns as service credits.'
            : 'Cancel this upcoming reservation? A confirmed reservation returns its full price as service credits.';
        if (!window.confirm(confirmationMessage)) {
            return;
        }

        button.disabled = true;
        if (reasonEl) reasonEl.disabled = true;
        try {
            const res = await fetch(`/lab-admin/reservations/${encodeURIComponent(key)}/cancel`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'Idempotency-Key': createReservationIdempotencyKey()
                },
                body: JSON.stringify({ reasonCode })
            });
            const body = await res.json().catch(() => ({}));
            if (res.status === 401) throw new Error('Unauthorized: check LAB_MANAGER_TOKEN.');
            if (res.status === 403) throw new Error('Access denied: provider reservation administration is not available.');
            if (!res.ok) throw new Error(body.error || `Cancellation failed (HTTP ${res.status}).`);
            showToast('Reservation cancellation submitted', 'success');
            await loadActionableReservations();
        } catch (err) {
            console.error(err);
            showToast(err.message || 'Reservation cancellation failed', 'error');
            button.disabled = false;
            if (reasonEl) reasonEl.disabled = false;
        }
    }

    function createReservationIdempotencyKey() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return `lab-manager-${window.crypto.randomUUID()}`;
        }
        return `lab-manager-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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
                <i class="fas fa-exclamation-triangle warning-icon"></i>
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
