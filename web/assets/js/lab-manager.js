// Utility function to escape HTML and prevent XSS attacks
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    const stateModule = window.LabManagerState;
    if (!stateModule) {
        throw new Error('LabManagerState must load before lab-manager.js');
    }
    const managerState = stateModule.createTabActivationState();
    const apiClientModule = window.LabManagerApiClient;
    if (!apiClientModule) {
        throw new Error('LabManagerApiClient must load before lab-manager.js');
    }
    const apiClient = apiClientModule.createClient({
        fetchImpl: (...args) => fetch(...args),
    });
    const requestJson = apiClient.requestJson;
    const activityModule = window.LabManagerActivity;
    if (!activityModule) {
        throw new Error('LabManagerActivity must load before lab-manager.js');
    }
    const accessPolicyModule = window.LabManagerAccessPolicy;
    if (!accessPolicyModule) {
        throw new Error('LabManagerAccessPolicy must load before lab-manager.js');
    }
    const accessPolicyController = accessPolicyModule.createController({
        document,
        fetchImpl: (...args) => fetch(...args),
    });
    const loadAccessPolicy = accessPolicyController.loadAccessPolicy;
    const heartbeatErrors = window.LabManagerHeartbeatErrors;
    if (!heartbeatErrors) {
        throw new Error('LabManagerHeartbeatErrors must load before lab-manager.js');
    }
    const formatHeartbeatStreamError = heartbeatErrors.formatStreamError;
    const isHeartbeatConfigurationError = heartbeatErrors.isConfigurationError;
    const hostsModule = window.LabManagerHosts;
    if (!hostsModule) {
        throw new Error('LabManagerHosts must load before lab-manager.js');
    }
    const hostDiscoveryModule = window.LabManagerHostDiscovery;
    if (!hostDiscoveryModule) {
        throw new Error('LabManagerHostDiscovery must load before lab-manager.js');
    }
    const winrmCredentialsModule = window.LabManagerWinrmCredentials;
    if (!winrmCredentialsModule) {
        throw new Error('LabManagerWinrmCredentials must load before lab-manager.js');
    }
    const winrmTrustModule = window.LabManagerWinrmTrust;
    if (!winrmTrustModule) {
        throw new Error('LabManagerWinrmTrust must load before lab-manager.js');
    }
    const hostProvisioningModule = window.LabManagerHostProvisioning;
    if (!hostProvisioningModule) {
        throw new Error('LabManagerHostProvisioning must load before lab-manager.js');
    }
    const hostActionsModule = window.LabManagerHostActions;
    if (!hostActionsModule) {
        throw new Error('LabManagerHostActions must load before lab-manager.js');
    }
    const toastModule = window.LabManagerToast;
    if (!toastModule) {
        throw new Error('LabManagerToast must load before lab-manager.js');
    }
    const toastController = toastModule.createController({
        document,
        setTimeoutImpl: setTimeout,
    });
    const showToast = toastController.showToast;
    const notificationsAccessModule = window.LabManagerNotificationsAccess;
    if (!notificationsAccessModule) {
        throw new Error('LabManagerNotificationsAccess must load before lab-manager.js');
    }
    const notificationsAccessController = notificationsAccessModule.createController({
        fetchImpl: (...args) => fetch(...args),
        applyNotificationConfig: (...args) => notificationsConfigController.applyConfig(...args),
        setNotificationsLocked,
        setStatus,
        updateBillingStatusAction,
        showToast,
        getAuthTokenHandler: () => window.AuthTokenHandler,
        logger: console,
    });
    const hasBillingAccess = notificationsAccessController.hasBillingAccess;
    const loadConfig = notificationsAccessController.loadConfig;
    const promptBillingToken = notificationsAccessController.promptBillingToken;
    const requestNotificationsAccess = notificationsAccessController.requestAccess;
    const requireBillingAccess = notificationsAccessController.requireAccess;
    const paginationModule = window.LabManagerPagination;
    if (!paginationModule) {
        throw new Error('LabManagerPagination must load before lab-manager.js');
    }
    const normalizePagination = paginationModule.normalizePagination;
    const formattersModule = window.LabManagerFormatters;
    if (!formattersModule) {
        throw new Error('LabManagerFormatters must load before lab-manager.js');
    }
    const formatDate = formattersModule.formatDate;
    const formatBool = formattersModule.formatBool;
    const htmlEscape = formattersModule.htmlEscape;
    const notificationsConfigModule = window.LabManagerNotificationsConfig;
    if (!notificationsConfigModule) {
        throw new Error('LabManagerNotificationsConfig must load before lab-manager.js');
    }
    const fmuSyncModule = window.LabManagerFmuSync;
    if (!fmuSyncModule) {
        throw new Error('LabManagerFmuSync must load before lab-manager.js');
    }
    const aasLinkModule = window.LabManagerAasLink;
    if (!aasLinkModule) {
        throw new Error('LabManagerAasLink must load before lab-manager.js');
    }
    const powerCredentialsModule = window.LabManagerPowerCredentials;
    if (!powerCredentialsModule) {
        throw new Error('LabManagerPowerCredentials must load before lab-manager.js');
    }
    const activityFeedController = activityModule.createController({
        document,
        fetchImpl: (...args) => fetch(...args),
        requestJson,
        escapeHtml,
        normalizePagination,
        logger: console,
    });
    const loadActivityFeed = activityFeedController.loadActivityFeed;
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
    const smtpSectionEl = $('#smtpSection');

    const graphTenantEl = $('#graphTenant');
    const graphClientIdEl = $('#graphClientId');
    const graphClientSecretEl = $('#graphClientSecret');
    const graphFromEl = $('#graphFrom');
    const graphSectionEl = $('#graphSection');
    const driverSummary = $('#driverSummary');
    const configStatusEl = $('#configStatus');
    const notificationsAccessGateEl = $('#notificationsAccessGate');
    const notificationsConfigContentEl = $('#notificationsConfigContent');
    const unlockNotificationsBtn = $('#unlockNotificationsBtn');
    const smtpPasswordHintEl = $('#smtpPasswordHint');
    const graphClientSecretHintEl = $('#graphClientSecretHint');

    const notificationsConfigController = notificationsConfigModule.createController({
        fields: {
            enabled: enabledEl,
            driver: driverEl,
            from: fromEl,
            fromName: fromNameEl,
            defaultTo: defaultToEl,
            timezone: timezoneEl,
            smtpHost: smtpHostEl,
            smtpPort: smtpPortEl,
            smtpUser: smtpUserEl,
            smtpPass: smtpPassEl,
            smtpStartTls: smtpStartTlsEl,
            graphTenant: graphTenantEl,
            graphClientId: graphClientIdEl,
            graphClientSecret: graphClientSecretEl,
            graphFrom: graphFromEl,
            smtpSection: smtpSectionEl,
            graphSection: graphSectionEl,
            driverSummary,
            smtpPasswordHint: smtpPasswordHintEl,
            graphClientSecretHint: graphClientSecretHintEl,
        },
        commonTimezones: COMMON_TIMEZONES,
        browserTimezone,
    });
    const applyNotificationConfig = notificationsConfigController.applyConfig;
    const buildNotificationPayload = notificationsConfigController.buildPayload;
    const populateTimezones = notificationsConfigController.populateTimezones;
    const toggleSections = notificationsConfigController.toggleSections;
    const updateDriverSummary = notificationsConfigController.updateDriverSummary;

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
    const winrmTrustModal = $('#winrmTrustModal');
    const closeWinrmTrustModalBtn = $('#closeWinrmTrustModal');
    const cancelWinrmTrustBtn = $('#cancelWinrmTrust');
    const previewWinrmTrustBtn = $('#previewWinrmTrust');
    const saveWinrmTrustBtn = $('#saveWinrmTrust');
    const verifyWinrmTrustBtn = $('#verifyWinrmTrust');
    const deleteWinrmTrustBtn = $('#deleteWinrmTrust');
    const winrmTrustModalHostEl = $('#winrmTrustModalHost');
    const winrmTrustCurrentEl = $('#winrmTrustCurrent');
    const winrmTrustCertificateEl = $('#winrmTrustCertificate');
    const winrmTrustCertificateNameEl = $('#winrmTrustCertificateName');
    const winrmTrustPreviewEl = $('#winrmTrustPreview');
    const winrmTrustPreviewDetailsEl = $('#winrmTrustPreviewDetails');
    const winrmTrustFingerprintConfirmedEl = $('#winrmTrustFingerprintConfirmed');
    const editHostModal = $('#editHostModal');
    const closeEditHostModalBtn = $('#closeEditHostModal');
    const cancelEditHostBtn = $('#cancelEditHost');
    const saveEditHostBtn = $('#saveEditHost');
    const winrmCredentialRefEl = $('#winrmCredentialRef');
    const winrmCredentialAddressEl = $('#winrmCredentialAddress');
    const winrmCredentialUserEl = $('#winrmCredentialUser');
    const winrmCredentialPasswordEl = $('#winrmCredentialPassword');
    const provisionConnectionIdEl = $('#provisionConnectionId');
    const provisionHostNameEl = $('#provisionHostName');
    const provisionHostNameCandidatesEl = $('#provisionHostNameCandidates');
    const provisionHostAddressEl = $('#provisionHostAddress');
    const provisionHostMacEl = $('#provisionHostMac');
    const provisionHeartbeatPathEl = $('#provisionHeartbeatPath');
    const editHostOriginalNameEl = $('#editHostOriginalName');
    const editHostNameEl = $('#editHostName');
    const editHostAddressEl = $('#editHostAddress');
    const editHostMacEl = $('#editHostMac');
    const editHeartbeatPathEl = $('#editHeartbeatPath');

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
    if (closeWinrmTrustModalBtn) closeWinrmTrustModalBtn.addEventListener('click', closeWinrmTrustModal);
    if (cancelWinrmTrustBtn) cancelWinrmTrustBtn.addEventListener('click', closeWinrmTrustModal);
    if (previewWinrmTrustBtn) previewWinrmTrustBtn.addEventListener('click', previewWinrmTrust);
    if (saveWinrmTrustBtn) saveWinrmTrustBtn.addEventListener('click', saveWinrmTrust);
    if (verifyWinrmTrustBtn) verifyWinrmTrustBtn.addEventListener('click', verifyWinrmTrust);
    if (deleteWinrmTrustBtn) deleteWinrmTrustBtn.addEventListener('click', deleteWinrmTrust);
    if (winrmTrustCertificateEl) winrmTrustCertificateEl.addEventListener('change', handleWinrmTrustCertificateSelected);
    if (winrmTrustFingerprintConfirmedEl) {
        winrmTrustFingerprintConfirmedEl.addEventListener('change', updateWinrmTrustSaveState);
    }
    if (closeEditHostModalBtn) closeEditHostModalBtn.addEventListener('click', closeEditHostModal);
    if (cancelEditHostBtn) cancelEditHostBtn.addEventListener('click', closeEditHostModal);
    if (saveEditHostBtn) saveEditHostBtn.addEventListener('click', saveEditedHost);

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
    const powerControllerProfileEl = $('#powerControllerProfile');
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
    let activeWinrmTrustHost = '';
    let savedWinrmTrustStatus = 'loading';
    let activeWinrmTrustFile = null;
    let activeWinrmTrustPreview = null;
    const guacamoleCandidateState = {};
    const guacamolePopoverClosers = new Set();
    const heartbeatSources = {};
    const heartbeatStreamErrorShown = {};
    let powerControllers = [];
    let powerControllerStatusLoading = false;
    let powerControllerStatusError = false;
    let powerControllerStatusRequestId = 0;
    let powerControllerOutletDrafts = [];
    let powerControllerIdWasSuggested = false;
    let lastPowerControllerDriver = 'mock';
    let powerCredentials = [];
    let powerPolicies = [];
    let powerPolicyStepDrafts = [];
    let managedLabsInitialized = false;
    let managedLabsPromise = null;
    let managedLabs = [];
    let hostNames = [];
    let guacamoleCandidates = [];
    let guacamoleStationCandidates = [];
    let provisionStationKey = '';
    let provisionLabsLoading = false;

    const hostsController = hostsModule.createController({
        fetchImpl: (...args) => fetch(...args),
        getEventSource: () => window.EventSource,
        getOrigin: () => window.location.origin,
        state: {
            hostState,
            hostMetadata,
            heartbeatSources,
            heartbeatStreamErrorShown,
            getHostNames: () => hostNames,
            setHostNames: nextHostNames => { hostNames = nextHostNames; },
        },
        callbacks: {
            renderHosts,
            loadActivityFeed,
            setGuacamoleCandidates: candidates => { guacamoleCandidates = candidates; },
            renderGuacamoleCandidates: candidates => {
                guacamoleStationCandidates = candidates;
                renderGuacamoleCandidates(candidates);
            },
            rememberGuacamoleCandidate,
            groupGuacamoleCandidates,
            updateOpsHint,
            showOpsWarning,
            showToast,
            formatHeartbeatStreamError,
            isHeartbeatConfigurationError,
        },
        logger: console,
    });
    const loadHostInventory = hostsController.loadInventory;
    const startHeartbeatStream = hostsController.startHeartbeatStream;
    const stopHeartbeatStream = hostsController.stopHeartbeatStream;
    const refreshAllHosts = hostsController.refreshAllHosts;
    const pollHeartbeat = hostsController.pollHeartbeat;
    const hostActionsController = hostActionsModule.createController({
        fetchImpl: (...args) => fetch(...args),
        callbacks: {
            pollHeartbeat,
            showToast,
        },
        logger: console,
    });
    const hostDiscoveryController = hostDiscoveryModule.createController({
        fetchImpl: (...args) => fetch(...args),
        candidateState: guacamoleCandidateState,
        callbacks: {
            renderCandidates: () => renderGuacamoleCandidates(guacamoleStationCandidates),
            loadHostInventory,
            showToast,
        },
        logger: console,
    });
    const winrmCredentialsController = winrmCredentialsModule.createController({
        fetchImpl: (...args) => fetch(...args),
        callbacks: {
            closeModal: closeWinrmCredentialsModal,
            loadHostInventory,
            showToast,
        },
        logger: console,
    });
    const winrmTrustController = winrmTrustModule.createController({
        fetchImpl: (...args) => fetch(...args),
        formDataCtor: FormData,
        formatErrorMessage: winrmTrustErrorMessage,
        callbacks: {
            onLoaded: (host, trust) => {
                if (activeWinrmTrustHost === host) renderWinrmTrustState(trust);
            },
            onLoadError: (host, err) => {
                if (activeWinrmTrustHost !== host) return;
                savedWinrmTrustStatus = 'unavailable';
                updateWinrmTrustVerifyState();
                if (winrmTrustCurrentEl) {
                    winrmTrustCurrentEl.textContent = `Unable to load trust: ${err.message}`;
                }
                showToast(`WinRM trust status failed: ${err.message}`, 'error');
            },
            onPreview: preview => {
                activeWinrmTrustPreview = preview;
                renderWinrmTrustPreview(preview);
            },
            onReady: preview => {
                activeWinrmTrustPreview = preview;
                renderWinrmTrustPreview(preview);
                showToast('Certificate preview ready; verify the SHA-256 fingerprint', 'success');
            },
            onPreviewError: err => showToast(`Certificate preview failed: ${err.message}`, 'error'),
            onPreviewFinished: updateWinrmTrustSaveState,
            onSaved: async host => {
                const savedHost = host;
                closeWinrmTrustModal();
                showToast(`WinRM TLS trust saved for ${savedHost}`, 'success');
                await loadHostInventory({ skipAuthPrompt: true });
                await pollHeartbeat(savedHost);
            },
            onSaveError: err => showToast(`WinRM trust save failed: ${err.message}`, 'error'),
            onSaveFinished: updateWinrmTrustSaveState,
            onRemoved: async host => {
                closeWinrmTrustModal();
                showToast(`WinRM TLS trust removed for ${host}`, 'success');
                await loadHostInventory({ skipAuthPrompt: true });
            },
            onRemoveError: (host, err) => showToast(`WinRM trust removal failed: ${err.message}`, 'error'),
            onRemoveFinished: () => {
                if (deleteWinrmTrustBtn) deleteWinrmTrustBtn.disabled = false;
            },
        },
    });
    const hostProvisioningController = hostProvisioningModule.createController({
        fetchImpl: (...args) => fetch(...args),
        callbacks: {
            closeModal: closeProvisionHostModal,
            loadHostInventory,
            showToast,
        },
        logger: console,
    });

    const powerCredentialsController = powerCredentialsModule.createController({
        fields: {
            select: powerCredentialSelectEl,
            ref: powerCredentialRefEl,
            type: powerCredentialTypeEl,
            username: powerCredentialUsernameEl,
            password: powerCredentialPasswordEl,
            community: powerCredentialCommunityEl,
            authProtocol: powerCredentialAuthProtocolEl,
            authPassword: powerCredentialAuthPasswordEl,
            privProtocol: powerCredentialPrivProtocolEl,
            privPassword: powerCredentialPrivPasswordEl,
            contextName: powerCredentialContextNameEl,
            usernameField: powerCredentialUsernameFieldEl,
            passwordField: powerCredentialPasswordFieldEl,
            communityField: powerCredentialCommunityFieldEl,
            authProtocolField: powerCredentialAuthProtocolFieldEl,
            authPasswordField: powerCredentialAuthPasswordFieldEl,
            privProtocolField: powerCredentialPrivProtocolFieldEl,
            privPasswordField: powerCredentialPrivPasswordFieldEl,
            contextNameField: powerCredentialContextNameFieldEl,
            saveButton: powerCredentialSaveBtn,
            list: powerCredentialsListEl,
            status: powerCredentialsStatusEl,
            hint: powerCredentialsHintEl,
            editorHint: powerCredentialEditorHintEl,
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
        showOpsWarning,
        refreshPowerControllerStatuses: (...args) => loadPowerControllerStatuses(...args),
        renderControllerCredentialOptions: credentials => {
            powerCredentials = credentials;
            renderPowerControllerCredentialOptions();
        },
        escapeHtml,
        documentImpl: document,
    });
    const loadPowerCredentials = powerCredentialsController.load;
    powerCredentialsController.initialize();

    // FMU AAS sync elements
    const fmuSyncBtn = $('#fmuSyncBtn');
    const fmuSyncKeyEl = $('#fmuSyncKey');
    const fmuSyncLabSelectEl = $('#fmuSyncLabSelect');
    const fmuSyncFileEl = $('#fmuSyncFile');
    const fmuSyncFileNameEl = $('#fmuSyncFileName');
    const fmuSyncResultEl = $('#fmuSyncResult');
    const fmuSyncDescriptionEl = $('#fmuSyncDescription');
    const fmuSyncLicenseEl = $('#fmuSyncLicense');
    const fmuSyncDocsUrlEl = $('#fmuSyncDocsUrl');
    const fmuSyncContactEmailEl = $('#fmuSyncContactEmail');
    const fmuSyncDescriptionHintEl = $('#fmuSyncDescriptionHint');
    const fmuSyncLicenseHintEl = $('#fmuSyncLicenseHint');

    const fmuSyncController = fmuSyncModule.createController({
        fields: {
            syncButton: fmuSyncBtn,
            keyInput: fmuSyncKeyEl,
            labSelect: fmuSyncLabSelectEl,
            fileInput: fmuSyncFileEl,
            fileName: fmuSyncFileNameEl,
            result: fmuSyncResultEl,
            description: fmuSyncDescriptionEl,
            license: fmuSyncLicenseEl,
            docsUrl: fmuSyncDocsUrlEl,
            contactEmail: fmuSyncContactEmailEl,
            descriptionHint: fmuSyncDescriptionHintEl,
            licenseHint: fmuSyncLicenseHintEl,
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
        formDataCtor: FormData,
        urlSearchParamsCtor: URLSearchParams,
        logger: console,
    });
    fmuSyncController.initialize();

    // AAS Link elements
    const aasLinkKeyEl = $('#aasLinkKey');
    const aasLinkLabSelectEl = $('#aasLinkLabSelect');
    const aasLinkAasIdEl = $('#aasLinkAasId');
    const aasLinkSaveBtn = $('#aasLinkSaveBtn');
    const aasLinkCheckBtn = $('#aasLinkCheckBtn');
    const aasLinkDeleteBtn = $('#aasLinkDeleteBtn');
    const aasLinkResultEl = $('#aasLinkResult');
    const aasLinkController = aasLinkModule.createController({
        fields: {
            keyInput: aasLinkKeyEl,
            labSelect: aasLinkLabSelectEl,
            aasIdInput: aasLinkAasIdEl,
            saveButton: aasLinkSaveBtn,
            checkButton: aasLinkCheckBtn,
            deleteButton: aasLinkDeleteBtn,
            result: aasLinkResultEl,
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
    });
    aasLinkController.initialize();

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
    if (refreshPowerControllersBtn) refreshPowerControllersBtn.addEventListener('click', () => {
        loadPowerControllers({ forceStatusRefresh: true });
    });
    if (powerControllerSelectEl) powerControllerSelectEl.addEventListener('change', loadSelectedPowerController);
    if (powerControllerDriverEl) {
        powerControllerDriverEl.addEventListener('change', updatePowerControllerDriverFields);
        powerControllerDriverEl.addEventListener('change', suggestPowerControllerId);
        powerControllerDriverEl.addEventListener('change', renderPowerControllerCredentialOptions);
    }
    if (powerControllerHostEl) powerControllerHostEl.addEventListener('input', suggestPowerControllerId);
    if (powerControllerIdEl) {
        powerControllerIdEl.addEventListener('input', () => {
            powerControllerIdWasSuggested = false;
        });
    }
    if (powerControllerNetioHttpsEl) powerControllerNetioHttpsEl.addEventListener('change', updatePowerControllerNetioPort);
    if (addPowerControllerOutletBtn) addPowerControllerOutletBtn.addEventListener('click', addPowerControllerOutlet);
    if (powerControllerOutletsEl) {
        powerControllerOutletsEl.addEventListener('change', handlePowerControllerOutletChange);
        powerControllerOutletsEl.addEventListener('input', handlePowerControllerOutletChange);
        powerControllerOutletsEl.addEventListener('click', handlePowerControllerOutletActions);
    }
    if (savePowerControllerBtn) savePowerControllerBtn.addEventListener('click', savePowerController);
    if (refreshPowerCredentialsBtn) refreshPowerCredentialsBtn.addEventListener('click', loadPowerCredentials);
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

    function setNotificationsLocked(locked) {
        if (notificationsAccessGateEl) notificationsAccessGateEl.hidden = !locked;
        if (notificationsConfigContentEl) notificationsConfigContentEl.hidden = locked;
        [configureBtn, $('#btnTestLoad'), $('#saveConfigBtn'), $('#btnTestEmail')]
            .filter(Boolean)
            .forEach(button => { button.disabled = locked; });
    }

    if (upcomingReservationsListEl) {
        upcomingReservationsListEl.addEventListener('click', handleUpcomingReservationActions);
        upcomingReservationsListEl.addEventListener('change', handleUpcomingReservationReasonChange);
    }

    document.addEventListener('lab-manager:tab-activated', event => {
        initializeManagerTab(event.detail && event.detail.tab);
    });
    if (window.LabManagerTabs && window.LabManagerTabs.activeTab) {
        initializeManagerTab(window.LabManagerTabs.activeTab);
    }

    async function refreshLabManagerSession() {
        try {
            // This protected Lab Manager request also refreshes the same
            // short-lived session cookie across /lab-admin and /ops.
            const res = await fetch('/lab-manager/access-policy', {
                credentials: 'same-origin',
                cache: 'no-store',
                skipAuthPrompt: true,
            });
            return res.ok;
        } catch (err) {
            console.warn('Unable to refresh Lab Manager session', err);
            return false;
        }
    }

    function initializeManagerTab(tabName) {
        if (!managerState.claimTab(tabName)) return;

        if (tabName === 'operations') {
            void (async () => {
                await refreshLabManagerSession();
                await loadManagedLabsOnce({ skipAuthPrompt: true });
                checkOpsAvailability();
                if (hostListEl) loadHostInventory({ skipAuthPrompt: true });
                if (upcomingReservationsListEl) loadActionableReservations({ skipAuthPrompt: true });
                // Let the shared auth handler recover an expired session and
                // retry this request. A valid Lab Manager session does not
                // prompt; suppressing the handler turns an expired session
                // into a misleading visible HTTP 401.
                loadActivityFeed(false);
            })();
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

    function loadManagedLabsOnce(options = {}) {
        if (managedLabsPromise) return managedLabsPromise;
        if (managedLabsInitialized) return Promise.resolve();
        managedLabsInitialized = true;
        managedLabsPromise = loadManagedLabs(options);
        return managedLabsPromise;
    }

    function saveConfig() {
        if (!hasBillingAccess()) {
            requireBillingAccess(() => saveConfig());
            return;
        }

        const payload = buildNotificationPayload();

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

    function openModal() {
        modal.classList.add('show');
    }

    function closeModal() {
        modal.classList.remove('show');
        updateDriverSummary();
    }

    function setStatus(text) {
        if (configStatusEl) {
            configStatusEl.textContent = text;
        }
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

    function $(sel) { return document.querySelector(sel); }

    // ---- Lab Station ops helpers ----
    function updateOpsHint(data) {
        const opsHint = $('#opsHint');
        if (!opsHint) return;
        if (!data) {
            opsHint.textContent = 'The ops inventory could not be loaded.';
            return;
        }
        const stationCount = groupGuacamoleCandidates(data.guacamoleUnmatched).length;
        const guacStatus = data.guacamoleAvailable
            ? `${stationCount} Lab Station candidate${stationCount === 1 ? '' : 's'} awaiting configuration.`
            : 'Guacamole inventory unavailable.';
        opsHint.textContent = `Hosts are loaded from ops-worker/hosts.json and ops-data/hosts.json. ${guacStatus}`;
    }

    async function loadPowerControllers(options = {}) {
        const { forceStatusRefresh = false, ...fetchOptions } = options;
        fetchOptions.cache = 'no-store';
        powerControllerStatusRequestId += 1;
        if (powerControllersStatusEl) {
            powerControllersStatusEl.textContent = 'Loading...';
            powerControllersStatusEl.className = 'pill soft';
        }
        try {
            const res = await fetch('/ops/api/power/controllers', fetchOptions);
            if (res.status === 403) {
                showOpsWarning();
                return false;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power controllers', 'error');
                return false;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            powerControllers = Array.isArray(body.controllers) ? body.controllers : [];
            powerControllerStatusLoading = powerControllers.length > 0;
            powerControllerStatusError = false;
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
            if (powerControllers.length) {
                void loadPowerControllerStatuses({
                    forceRefresh: forceStatusRefresh,
                    skipAuthPrompt: options.skipAuthPrompt,
                });
            }
            return true;
        } catch (err) {
            console.warn('Unable to load power controllers', err);
            powerControllers = [];
            powerControllerStatusLoading = false;
            powerControllerStatusError = false;
            renderPowerControllers();
            renderPowerControllerOptions();
            renderPowerPolicySteps();
            if (powerControllersStatusEl) {
                powerControllersStatusEl.textContent = 'Unavailable';
                powerControllersStatusEl.className = 'pill bad';
            }
            if (powerControllersHintEl) powerControllersHintEl.textContent = 'Power controllers could not be loaded.';
            return false;
        }
    }

    async function loadPowerControllerStatuses(options = {}) {
        const { forceRefresh = false, ...fetchOptions } = options;
        fetchOptions.cache = 'no-store';
        const requestId = ++powerControllerStatusRequestId;
        if (!powerControllers.length) {
            powerControllerStatusLoading = false;
            powerControllerStatusError = false;
            renderPowerControllers();
            return;
        }
        powerControllerStatusLoading = true;
        powerControllerStatusError = false;
        renderPowerControllers();
        const query = forceRefresh ? '?refresh=true' : '';
        try {
            const res = await fetch(`/ops/api/power/controllers/status${query}`, fetchOptions);
            if (res.status === 403) {
                showOpsWarning();
                throw new Error('Power controller status access denied');
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power controller status', 'error');
                throw new Error('Lab Manager session required');
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            if (!Array.isArray(body.controllers)) throw new Error('Power controller status is invalid');
            if (requestId !== powerControllerStatusRequestId) return;
            const statuses = new Map(
                body.controllers
                    .filter(controller => controller && controller.id)
                    .map(controller => [String(controller.id), controller]),
            );
            powerControllers = powerControllers.map(controller => {
                const status = statuses.get(String(controller.id));
                if (!status) return controller;
                const statusOutlets = new Map(
                    (Array.isArray(status.outlets) ? status.outlets : [])
                        .filter(outlet => outlet && outlet.outlet !== undefined)
                        .map(outlet => [String(outlet.outlet), outlet]),
                );
                return {
                    ...controller,
                    discovery: status.discovery || {},
                    outlets: (Array.isArray(controller.outlets) ? controller.outlets : []).map(outlet => ({
                        ...outlet,
                        state: statusOutlets.get(String(outlet.outlet))?.state || 'unknown',
                    })),
                };
            });
            powerControllerStatusError = false;
        } catch (err) {
            if (requestId !== powerControllerStatusRequestId) return;
            console.warn('Unable to load power controller status', err);
            powerControllerStatusError = true;
        } finally {
            if (requestId === powerControllerStatusRequestId) {
                powerControllerStatusLoading = false;
                renderPowerControllers();
            }
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
                managedLabs = [];
                renderPowerPolicyLabOptions([]);
                renderFmuAccessKeyOptions([]);
                renderFmuLabOptions(fmuSyncLabSelectEl, []);
                renderFmuLabOptions(aasLinkLabSelectEl, []);
                return;
            }
            if (res.status === 401) {
                if (!options.skipAuthPrompt) showToast('Lab Manager session required to load laboratories', 'error');
                managedLabs = [];
                renderPowerPolicyLabOptions([]);
                renderFmuAccessKeyOptions([]);
                renderFmuLabOptions(fmuSyncLabSelectEl, []);
                renderFmuLabOptions(aasLinkLabSelectEl, []);
                return;
            }
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
            managedLabs = Array.isArray(body.labs) ? body.labs : [];
            renderPowerPolicyLabOptions(managedLabs, selectedPowerPolicyLabId);
            renderFmuAccessKeyOptions(managedLabs, selectedFmuAccessKey);
            renderFmuLabOptions(fmuSyncLabSelectEl, managedLabs, selectedFmuLabId);
            renderFmuLabOptions(aasLinkLabSelectEl, managedLabs, selectedAasLinkLabId);
        } catch (err) {
            console.warn('Unable to load provider laboratories', err);
            managedLabs = [];
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
            option.textContent = `${resolveLabDisplayName(lab)} · ${accessKey}`;
            fmuSyncKeyEl.appendChild(option);
        });
        const selected = preferredAccessKey || current || '';
        fmuSyncKeyEl.value = accessKeys.some(lab => String(lab.accessKey) === selected)
            ? selected
            : '';
        fmuSyncKeyEl.disabled = accessKeys.length === 0;
    }

    function formatPowerPolicyLabLabel(lab) {
        const resourceType = Number(lab?.resourceType) === 1 ? 'FMU' : 'Remote';
        const status = lab?.listed ? 'Listed' : 'Draft';
        return `${resolveLabDisplayName(lab)} · ${resourceType} · ${status}`;
    }

    function resolveLabDisplayName(lab) {
        const candidates = [
            lab?.name,
            lab?.labName,
            lab?.metadataName,
            lab?.metadata?.name,
            lab?.metadata?.labName,
        ];
        const name = candidates.find(candidate => typeof candidate === 'string' && candidate.trim());
        const labId = String(lab?.labId ?? '').trim();
        return name ? name.trim() : `Lab #${labId}`;
    }

    function resolveReservationLabDisplayName(reservation) {
        const directName = [reservation?.labName, reservation?.name]
            .find(candidate => typeof candidate === 'string' && candidate.trim());
        if (directName) return directName.trim();
        const managedLab = managedLabs.find(lab => String(lab?.labId ?? '') === String(reservation?.labId ?? ''));
        return resolveLabDisplayName(managedLab || reservation);
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
            const lab = managedLabs.find(item => String(item?.labId || '') === String(policy.labId || ''))
                || { labId: policy.labId };
            option.textContent = `${resolveLabDisplayName(lab)} · ${policy.policyName || 'Unnamed policy'}`;
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
        if (powerPolicyEditorHintEl) powerPolicyEditorHintEl.textContent = '';
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
    }

    function updatePowerControllerNetioPort() {
        if (powerControllerDriverEl?.value !== 'netio-json' || !powerControllerPortEl) return;
        if (['80', '443'].includes(String(powerControllerPortEl.value || ''))) {
            powerControllerPortEl.value = powerControllerNetioHttpsEl?.checked === true ? '443' : '80';
        }
    }

    function suggestPowerControllerId() {
        if (!powerControllerIdEl || powerControllerSelectEl?.value) return;
        const host = String(powerControllerHostEl?.value || '').trim().toLowerCase();
        if (!host) {
            if (powerControllerIdWasSuggested) {
                powerControllerIdEl.value = '';
                powerControllerIdWasSuggested = false;
            }
            return;
        }
        const driver = powerControllerDriverEl?.value || 'mock';
        const prefix = driver === 'apc-powernet-snmp'
            ? 'apc'
            : driver === 'netio-json'
                ? 'netio'
                : 'power';
        const hostSlug = host.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 110);
        if (!hostSlug) return;
        const suggestion = `${prefix}-${hostSlug}`;
        const current = String(powerControllerIdEl.value || '').trim();
        if (!current || powerControllerIdWasSuggested) {
            powerControllerIdEl.value = suggestion;
            powerControllerIdWasSuggested = true;
        }
    }

    function resetPowerControllerEditor() {
        if (powerControllerSelectEl) powerControllerSelectEl.value = '';
        powerControllerIdWasSuggested = false;
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
        if (powerControllerTimeoutSecondsEl) powerControllerTimeoutSecondsEl.value = '2';
        if (powerControllerRetriesEl) powerControllerRetriesEl.value = '1';
        updatePowerControllerDriverFields();
        renderPowerControllerCredentialOptions();
        powerControllerOutletDrafts = [createPowerControllerOutletDraft({ outlet: '1' })];
        renderPowerControllerOutlets();
        if (powerControllerEditorHintEl) powerControllerEditorHintEl.textContent = '';
    }

    function populatePowerControllerForm(controller) {
        powerControllerIdWasSuggested = false;
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
        if (powerControllerTimeoutSecondsEl) powerControllerTimeoutSecondsEl.value = config.timeoutSeconds || '2';
        if (powerControllerRetriesEl) powerControllerRetriesEl.value = config.retries ?? '1';
        updatePowerControllerDriverFields();
        renderPowerControllerCredentialOptions();
        powerControllerOutletDrafts = Array.isArray(controller.outlets)
            ? controller.outlets.map(createPowerControllerOutletDraft)
            : [];
        renderPowerControllerOutlets();
    }

    function renderPowerControllerOptions() {
        if (!powerControllerSelectEl) return;
        const current = powerControllerSelectEl.value;
        powerControllerSelectEl.innerHTML = '<option value="">New controller</option>';
        powerControllers.forEach(controller => {
            const option = document.createElement('option');
            option.value = controller.id || '';
            option.textContent = controller.name || controller.id || 'Unnamed controller';
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

    function renderPowerControllerCredentialOptions() {
        if (!powerControllerCredentialRefEl) return;
        const driver = powerControllerDriverEl?.value || 'mock';
        const current = String(powerControllerCredentialRefEl.value || '').trim();
        const compatibleTypes = driver === 'apc-powernet-snmp'
            ? new Set(['snmpv1', 'snmpv2c', 'snmpv3'])
            : driver === 'netio-json'
                ? new Set(['netio-http-basic'])
                : null;
        const credentials = powerCredentials.filter(credential => {
            const reference = String(credential?.credentialRef || '').trim();
            if (!reference) return false;
            return !compatibleTypes || compatibleTypes.has(String(credential.type || '').trim().toLowerCase());
        });
        const currentIsCompatible = credentials.some(credential =>
            String(credential.credentialRef || '').trim() === current);
        const emptyLabel = driver === 'apc-powernet-snmp'
            ? 'Select SNMP credential'
            : driver === 'netio-json'
                ? 'No credential (optional)'
                : 'No credential required';
        const options = [`<option value="">${emptyLabel}</option>`];
        if (current && !currentIsCompatible) {
            options.push(`<option value="${escapeHtml(current)}">${escapeHtml(current)} — unavailable for this driver</option>`);
        }
        credentials.forEach(credential => {
            const reference = String(credential.credentialRef || '').trim();
            const type = String(credential.type || 'unknown').trim();
            options.push(`<option value="${escapeHtml(reference)}">${escapeHtml(reference)} · ${escapeHtml(type)}</option>`);
        });
        powerControllerCredentialRefEl.innerHTML = options.join('');
        powerControllerCredentialRefEl.value = current;
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
                timeoutSeconds,
                retries,
            };
        if (driver === 'netio-json' && (!config.path || !config.path.startsWith('/') || config.path.includes('\n') || config.path.includes('\r'))) {
            throw new Error('NETIO API path must start with /');
        }
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
            await loadPowerControllers({ skipAuthPrompt: true, forceStatusRefresh: true });
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
            const discoveryText = powerControllerStatusLoading
                ? 'checking'
                : powerControllerStatusError
                    ? 'status unavailable'
                    : reachable
                        ? 'reachable'
                        : discovery.errorCode ? `unreachable (${discovery.errorCode})` : 'unknown reachability';
            const discoveryClass = powerControllerStatusLoading
                ? 'soft'
                : powerControllerStatusError
                    ? 'warn'
                    : reachable ? 'good' : 'warn';
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
                    <span class="pill ${discoveryClass}">${safeDiscovery}</span>
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
            void loadPowerControllerStatuses({ forceRefresh: true, skipAuthPrompt: true });
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

    function closeAllGuacamoleMatchPopovers() {
        Array.from(guacamolePopoverClosers).forEach(closePopover => closePopover());
    }

    function setupGuacamoleMatchPopover(row) {
        const trigger = row.querySelector?.('.guacamole-match-trigger');
        const popover = row.querySelector?.('.guacamole-match-popover');
        if (!trigger || !popover || !document.body) return;

        let hideTimer = null;
        let isShown = false;

        function clearHideTimer() {
            if (hideTimer === null) return;
            window.clearTimeout(hideTimer);
            hideTimer = null;
        }

        function positionPopover() {
            if (!isShown) return;

            const triggerRect = trigger.getBoundingClientRect();
            const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
            const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
            const viewportMargin = 12;
            const popoverWidth = popover.offsetWidth;
            const popoverHeight = popover.offsetHeight;
            let left = triggerRect.left;
            let top = triggerRect.bottom + 8;

            if (
                top + popoverHeight > viewportHeight - viewportMargin
                && triggerRect.top - popoverHeight - 8 >= viewportMargin
            ) {
                top = triggerRect.top - popoverHeight - 8;
            }
            left = Math.min(
                Math.max(viewportMargin, left),
                Math.max(viewportMargin, viewportWidth - popoverWidth - viewportMargin),
            );
            popover.style.left = Math.round(left) + 'px';
            popover.style.top = Math.round(top) + 'px';
        }

        function closePopover() {
            clearHideTimer();
            isShown = false;
            popover.classList.remove('is-visible');
            popover.style.left = '';
            popover.style.top = '';
            if (popover.parentElement === document.body) popover.remove();
            window.removeEventListener('resize', positionPopover);
            window.removeEventListener('scroll', positionPopover, true);
            guacamolePopoverClosers.delete(closePopover);
        }

        function showPopover() {
            clearHideTimer();
            if (popover.parentElement !== document.body) document.body.appendChild(popover);
            isShown = true;
            guacamolePopoverClosers.add(closePopover);
            popover.classList.add('is-visible');
            positionPopover();
            window.addEventListener('resize', positionPopover);
            window.addEventListener('scroll', positionPopover, true);
        }

        function scheduleClosePopover() {
            clearHideTimer();
            hideTimer = window.setTimeout(() => {
                const triggerHovered = trigger.matches?.(':hover');
                const popoverHovered = popover.matches?.(':hover');
                const triggerFocused = document.activeElement === trigger;
                if (triggerHovered || popoverHovered || triggerFocused) return;
                closePopover();
            }, 120);
        }

        trigger.addEventListener('mouseenter', showPopover);
        trigger.addEventListener('mouseleave', scheduleClosePopover);
        trigger.addEventListener('focusin', showPopover);
        trigger.addEventListener('focusout', scheduleClosePopover);
        trigger.addEventListener('keydown', event => {
            if (event.key === 'Escape') closePopover();
        });
        popover.addEventListener('mouseenter', showPopover);
        popover.addEventListener('mouseleave', scheduleClosePopover);
    }

    function renderHosts() {
        if (!hostListEl) return;
        closeAllGuacamoleMatchPopovers();
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
        const hasHeartbeat = Boolean(updated);
        const winrmTrust = getWinrmTrustDisplay(meta);

        // Escape all user-controlled data to prevent XSS
        const safeHost = escapeHtml(host);
        const safeAddress = escapeHtml(meta.address) || 'n/a';
        const canEdit = meta.editable === true;
        const safeUpdated = escapeHtml(formatHostDate(updated, hasHeartbeat));
        const safeLastForced = escapeHtml(formatLastForcedLogoff(lastForced, hasHeartbeat));
        const safeLastPower = escapeHtml(formatLastPowerAction(lastPower, hasHeartbeat));
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

        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.host = host;
        row.innerHTML = `
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
                    <span class="pill ${ready === true ? 'good' : ready === false ? 'bad' : 'soft'}">Ready: ${formatBool(ready)}</span>
                    <span class="pill ${localSession === true ? 'warn' : 'soft'}">Local session: ${formatBool(localSession)}</span>
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
        setupGuacamoleMatchPopover(row);
        return row;
    }

    function renderGuacamoleCandidates(candidates) {
        if (!guacamoleCandidateListEl) return;
        guacamoleCandidateListEl.innerHTML = '';
        if (!Array.isArray(candidates) || !candidates.length) {
            guacamoleCandidateListEl.innerHTML = '<div class="empty">All Lab Station candidates are configured or no connections are available.</div>';
            return;
        }
        candidates.forEach(station => {
            guacamoleCandidateListEl.appendChild(buildGuacamoleCandidateRow(station));
        });
    }

    function buildGuacamoleCandidateRow(station) {
        const state = guacamoleCandidateState[station.key] || {};
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
        const row = document.createElement('div');
        row.className = 'host-row';
        row.dataset.stationKey = station.key;
        row.innerHTML = `
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
        const stationKey = row?.dataset.stationKey;
        if (!stationKey) return;
        if (btn.dataset.action === 'configure-candidate') {
            openProvisionHostModal(stationKey);
            return;
        }
        if (btn.dataset.action !== 'probe-candidate') return;
        const station = findGuacamoleStationCandidate(stationKey);
        if (!station) return;
        await hostDiscoveryController.probe(stationKey, station, btn);
    }

    function stationCandidateKey(candidate) {
        const address = normalizeMatchValue(candidate?.hostname);
        return address ? `host:${address}` : `connection:${String(candidate?.id ?? '')}`;
    }

    function groupGuacamoleCandidates(candidates) {
        const groups = new Map();
        (Array.isArray(candidates) ? candidates : []).forEach(candidate => {
            const key = stationCandidateKey(candidate);
            if (!key || key.endsWith(':')) return;
            let station = groups.get(key);
            if (!station) {
                station = {
                    key,
                    address: candidate?.hostname || '',
                    nameCandidates: [],
                    connections: []
                };
                groups.set(key, station);
            }
            station.connections.push(candidate);
            const name = String(candidate?.name || '').trim();
            if (name && !station.nameCandidates.includes(name)) {
                station.nameCandidates.push(name);
            }
        });
        return Array.from(groups.values());
    }

    function findGuacamoleStationCandidate(stationKey) {
        return guacamoleStationCandidates.find(station => station.key === stationKey)
            || null;
    }

    function rememberGuacamoleCandidate(candidate) {
        const key = stationCandidateKey(candidate);
        if (!key || key.endsWith(':')) return;
        guacamoleCandidateState[key] = {
            ...(guacamoleCandidateState[key] || {}),
            candidate: guacamoleCandidateState[key]?.candidate || candidate,
            connectionId: guacamoleCandidateState[key]?.connectionId || candidate?.id
        };
    }

    function normalizeMatchValue(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function urlOrigin(value) {
        const raw = (value || '').toString().trim();
        if (!raw) return '';
        try {
            return normalizeMatchValue(new URL(raw, window.location.origin).origin);
        } catch (_) {
            return '';
        }
    }

    function currentGatewayOrigin() {
        return urlOrigin(window.location.origin);
    }

    function labMatchesConnection(lab, connection) {
        if (Number(lab?.resourceType) !== 0) return false;

        const expectedAccessKey = normalizeMatchValue(
            connection?.selector || (connection?.id ? `guac:id:${connection.id}` : '')
        );
        const labAccessKey = normalizeMatchValue(lab?.accessKey);
        if (!expectedAccessKey || labAccessKey !== expectedAccessKey) return false;

        const gatewayOrigin = currentGatewayOrigin();
        const labOrigin = urlOrigin(lab?.accessURI);
        return Boolean(gatewayOrigin && labOrigin && labOrigin === gatewayOrigin);
    }

    async function loadLabCandidates() {
        const res = await fetch('/lab-admin/labs');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json().catch(() => ({}));
        return Array.isArray(body.labs) ? body.labs : [];
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

    async function populateProvisionLabCandidates(stationKey, station) {
        provisionLabsLoading = true;
        if (saveProvisionHostBtn) saveProvisionHostBtn.disabled = true;
        try {
            const labs = await loadLabCandidates();
            const candidateLabs = labs.filter(lab => station.connections.some(connection => (
                labMatchesConnection(lab, connection)
            )));
            const labIds = candidateLabs
                .map(lab => String(lab?.labId || '').trim())
                .filter(Boolean)
                .filter((labId, index, values) => values.indexOf(labId) === index);
            guacamoleCandidateState[stationKey] = {
                ...(guacamoleCandidateState[stationKey] || {}),
                labs: labIds,
                labCandidatesLoaded: true
            };
        } catch (err) {
            console.warn('Unable to load lab candidates', err);
            guacamoleCandidateState[stationKey] = {
                ...(guacamoleCandidateState[stationKey] || {}),
                labs: [],
                labCandidatesLoaded: true,
                labCandidatesError: err.message
            };
        } finally {
            provisionLabsLoading = false;
            if (saveProvisionHostBtn) saveProvisionHostBtn.disabled = false;
        }
    }

    function openProvisionHostModal(stationKey) {
        const station = findGuacamoleStationCandidate(stationKey);
        if (
            !station ||
            !provisionHostModal ||
            !provisionConnectionIdEl ||
            !provisionHostNameEl ||
            !provisionHostAddressEl ||
            !provisionHostMacEl ||
            !provisionHeartbeatPathEl
        ) {
            showToast('Host provisioning modal is unavailable', 'error');
            return;
        }
        const representative = station.connections[0];
        const state = guacamoleCandidateState[stationKey] || {};
        const draft = state.opsHostDraft || {};
        const host = station.address || station.nameCandidates[0] || '';
        provisionStationKey = stationKey;
        provisionConnectionIdEl.value = String(state.connectionId || representative?.id || '');
        provisionHostNameEl.value = draft.name || host;
        renderProvisionNameCandidates(draft.nameCandidates || station.nameCandidates);
        provisionHostAddressEl.value = draft.address || station.address || '';
        provisionHostMacEl.value = draft.mac || '';
        populateProvisionLabCandidates(stationKey, station);
        provisionHeartbeatPathEl.value = draft.heartbeat_path || 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json';
        provisionHostModal.classList.add('show');
    }

    function closeProvisionHostModal() {
        if (provisionHostModal) {
            provisionHostModal.classList.remove('show');
        }
    }

    function openEditHostModal(host) {
        const meta = hostMetadata[host] || {};
        if (
            !meta.editable ||
            !editHostModal ||
            !editHostOriginalNameEl ||
            !editHostNameEl ||
            !editHostAddressEl ||
            !editHostMacEl ||
            !editHeartbeatPathEl
        ) {
            showToast('Only dynamically configured hosts can be edited', 'error');
            return;
        }
        editHostOriginalNameEl.value = host;
        editHostNameEl.value = meta.name || host;
        editHostAddressEl.value = meta.address || host;
        editHostMacEl.value = meta.mac || '';
        editHeartbeatPathEl.value = meta.heartbeatPath || 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json';
        editHostModal.classList.add('show');
    }

    function closeEditHostModal() {
        if (editHostModal) {
            editHostModal.classList.remove('show');
        }
    }

    async function saveEditedHost() {
        if (
            !editHostOriginalNameEl ||
            !editHostNameEl ||
            !editHostMacEl ||
            !editHeartbeatPathEl
        ) {
            showToast('Host edit modal is unavailable', 'error');
            return;
        }
        const originalName = editHostOriginalNameEl.value.trim();
        const payload = {
            name: editHostNameEl.value.trim(),
            mac: editHostMacEl.value.trim(),
            heartbeatPath: editHeartbeatPathEl.value.trim(),
        };
        if (!originalName || !payload.name) {
            showToast('Name is required', 'error');
            return;
        }
        if (!/^[A-Za-z0-9._-]+$/.test(payload.name)) {
            showToast('Name must contain only letters, numbers, dots, underscores, and hyphens', 'error');
            return;
        }
        if (payload.mac && !/^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/.test(payload.mac)) {
            showToast('MAC must use format 00:11:22:33:44:55 or 00-11-22-33-44-55', 'error');
            return;
        }
        if (!payload.heartbeatPath) {
            showToast('Heartbeat path is required', 'error');
            return;
        }
        if (saveEditHostBtn) saveEditHostBtn.disabled = true;
        try {
            const res = await fetch(`/ops/api/hosts/${encodeURIComponent(originalName)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                const requestSuffix = body.requestId ? ` (request ID ${body.requestId})` : '';
                throw new Error(`${body.error || `HTTP ${res.status}`}${requestSuffix}`);
            }
            stopHeartbeatStream(originalName);
            delete hostState[originalName];
            closeEditHostModal();
            showToast(`Ops host ${body.host?.name || payload.name} updated`, 'success');
            await loadHostInventory({ skipAuthPrompt: true });
        } catch (err) {
            console.error(err);
            showToast(`Edit host failed: ${err.message}`, 'error');
        } finally {
            if (saveEditHostBtn) saveEditHostBtn.disabled = false;
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
            password: winrmCredentialPasswordEl.value,
        };
        await winrmCredentialsController.save(payload, saveWinrmCredentialsBtn);
    }

    function winrmTrustStatusLabel(status) {
        const labels = {
            missing: 'missing',
            ready: 'ready',
            expired: 'expired',
            'not-yet-valid': 'not yet valid',
            invalid: 'invalid',
            unavailable: 'unavailable',
        };
        return labels[String(status || '').trim().toLowerCase()] || 'unavailable';
    }

    function winrmTrustStatusClass(status) {
        const normalized = String(status || '').trim().toLowerCase();
        if (normalized === 'ready') return 'good';
        if (normalized === 'missing' || normalized === 'unavailable') return 'warn';
        return 'bad';
    }

    function appendTrustDetail(container, label, value) {
        const item = document.createElement('div');
        item.className = 'certificate-detail';
        const labelEl = document.createElement('dt');
        labelEl.textContent = label;
        const valueEl = document.createElement('dd');
        valueEl.textContent = value === null || value === undefined || value === '' ? 'n/a' : String(value);
        item.append(labelEl, valueEl);
        container.appendChild(item);
    }

    function renderWinrmTrustState(trust) {
        const status = String(trust?.status || (trust?.configured ? 'ready' : 'missing'))
            .trim()
            .toLowerCase();
        savedWinrmTrustStatus = status;
        updateWinrmTrustVerifyState();
        if (!winrmTrustCurrentEl) return;
        winrmTrustCurrentEl.className = `winrm-trust-current ${winrmTrustStatusClass(status)}`;
        winrmTrustCurrentEl.replaceChildren();

        const title = document.createElement('strong');
        title.textContent = `Current trust: ${winrmTrustStatusLabel(status)}`;
        winrmTrustCurrentEl.appendChild(title);

        const details = document.createElement('dl');
        details.className = 'certificate-detail-grid';
        appendTrustDetail(details, 'SHA-256', trust?.fingerprintSha256);
        appendTrustDetail(details, 'SHA-1', trust?.fingerprintSha1);
        appendTrustDetail(details, 'Subject', trust?.subject);
        appendTrustDetail(details, 'SAN DNS', Array.isArray(trust?.sanDnsNames) ? trust.sanDnsNames.join(', ') : '');
        appendTrustDetail(details, 'SAN IP', Array.isArray(trust?.sanIpAddresses) ? trust.sanIpAddresses.join(', ') : '');
        appendTrustDetail(details, 'Valid until', trust?.notAfter ? formatDate(trust.notAfter) : '');
        appendTrustDetail(details, 'Last validated', trust?.lastValidatedAt ? formatDate(trust.lastValidatedAt) : '');
        appendTrustDetail(details, 'Error code', trust?.errorCode);
        winrmTrustCurrentEl.appendChild(details);
    }

    function renderWinrmTrustPreview(preview) {
        if (!winrmTrustPreviewEl || !winrmTrustPreviewDetailsEl) return;
        winrmTrustPreviewEl.hidden = !preview;
        winrmTrustPreviewDetailsEl.replaceChildren();
        if (!preview) {
            updateWinrmTrustSaveState();
            return;
        }

        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Status', winrmTrustStatusLabel(preview.status));
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'SHA-256', preview.fingerprintSha256);
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'SHA-1', preview.fingerprintSha1);
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Subject', preview.subject);
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Issuer', preview.issuer);
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'SAN DNS', Array.isArray(preview.sanDnsNames) ? preview.sanDnsNames.join(', ') : '');
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'SAN IP', Array.isArray(preview.sanIpAddresses) ? preview.sanIpAddresses.join(', ') : '');
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Valid from', preview.notBefore ? formatDate(preview.notBefore) : '');
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Valid until', preview.notAfter ? formatDate(preview.notAfter) : '');
        appendTrustDetail(winrmTrustPreviewDetailsEl, 'Format', preview.format);
        if (winrmTrustFingerprintConfirmedEl) winrmTrustFingerprintConfirmedEl.checked = false;
        updateWinrmTrustSaveState();
    }

    function updateWinrmTrustVerifyState() {
        if (!verifyWinrmTrustBtn) return;
        verifyWinrmTrustBtn.disabled = !(
            activeWinrmTrustHost &&
            hostMetadata[activeWinrmTrustHost]?.winrmConfigured === true &&
            savedWinrmTrustStatus === 'ready'
        );
    }

    function updateWinrmTrustSaveState() {
        if (previewWinrmTrustBtn) previewWinrmTrustBtn.disabled = !activeWinrmTrustFile;
        if (saveWinrmTrustBtn) {
            saveWinrmTrustBtn.disabled = !(
                activeWinrmTrustFile &&
                activeWinrmTrustPreview?.valid === true &&
                winrmTrustFingerprintConfirmedEl?.checked === true
            );
        }
        updateWinrmTrustVerifyState();
    }

    function handleWinrmTrustCertificateSelected() {
        activeWinrmTrustFile = winrmTrustCertificateEl?.files?.[0] || null;
        activeWinrmTrustPreview = null;
        if (winrmTrustCertificateNameEl) {
            winrmTrustCertificateNameEl.textContent = activeWinrmTrustFile?.name || 'No file selected';
        }
        renderWinrmTrustPreview(null);
        updateWinrmTrustSaveState();
    }

    function winrmTrustErrorMessage(body, status) {
        const code = String(body?.code || '').trim();
        const requestSuffix = body?.requestId ? ` (request ID ${body.requestId})` : '';
        return `${body?.error || `HTTP ${status}`}${code ? ` [${code}]` : ''}${requestSuffix}`;
    }

    async function openWinrmTrustModal(host) {
        if (!winrmTrustModal || !winrmTrustCertificateEl) {
            showToast('WinRM TLS trust modal is unavailable', 'error');
            return;
        }
        activeWinrmTrustHost = host;
        savedWinrmTrustStatus = 'loading';
        activeWinrmTrustFile = null;
        activeWinrmTrustPreview = null;
        winrmTrustCertificateEl.value = '';
        if (winrmTrustCertificateNameEl) winrmTrustCertificateNameEl.textContent = 'No file selected';
        if (winrmTrustModalHostEl) {
            const meta = hostMetadata[host] || {};
            winrmTrustModalHostEl.textContent = `Host: ${host} · Address: ${meta.address || 'n/a'}`;
        }
        if (winrmTrustFingerprintConfirmedEl) winrmTrustFingerprintConfirmedEl.checked = false;
        renderWinrmTrustPreview(null);
        if (winrmTrustCurrentEl) winrmTrustCurrentEl.textContent = 'Loading certificate trust state...';
        updateWinrmTrustSaveState();
        winrmTrustModal.classList.add('show');
        await loadWinrmTrustState(host);
    }

    async function loadWinrmTrustState(host) {
        return winrmTrustController.load(host);
    }

    function closeWinrmTrustModal() {
        if (winrmTrustModal) winrmTrustModal.classList.remove('show');
        activeWinrmTrustHost = '';
        savedWinrmTrustStatus = 'unavailable';
        activeWinrmTrustFile = null;
        activeWinrmTrustPreview = null;
        updateWinrmTrustSaveState();
    }

    async function previewWinrmTrust() {
        if (!activeWinrmTrustHost || !activeWinrmTrustFile) {
            showToast('Choose a station certificate first', 'error');
            return;
        }
        if (previewWinrmTrustBtn) previewWinrmTrustBtn.disabled = true;
        await winrmTrustController.preview(activeWinrmTrustHost, activeWinrmTrustFile);
    }

    async function saveWinrmTrust() {
        if (!activeWinrmTrustHost || !activeWinrmTrustFile || activeWinrmTrustPreview?.valid !== true) {
            showToast('Preview a valid certificate first', 'error');
            return;
        }
        if (!winrmTrustFingerprintConfirmedEl?.checked) {
            showToast('Verify the SHA-256 fingerprint before saving', 'error');
            return;
        }
        if (saveWinrmTrustBtn) saveWinrmTrustBtn.disabled = true;
        await winrmTrustController.save(
            activeWinrmTrustHost,
            activeWinrmTrustFile,
            activeWinrmTrustPreview,
        );
    }

    async function verifyWinrmTrust() {
        if (!activeWinrmTrustHost || verifyWinrmTrustBtn?.disabled) return;
        await pollHeartbeat(activeWinrmTrustHost);
    }

    async function deleteWinrmTrust() {
        if (!activeWinrmTrustHost) return;
        if (!window.confirm(`Remove WinRM TLS trust for ${activeWinrmTrustHost}?`)) return;
        if (deleteWinrmTrustBtn) deleteWinrmTrustBtn.disabled = true;
        await winrmTrustController.remove(activeWinrmTrustHost);
    }

    async function saveProvisionedHost() {
        if (
            !provisionConnectionIdEl ||
            !provisionHostNameEl ||
            !provisionHostAddressEl ||
            !provisionHostMacEl ||
            !provisionHeartbeatPathEl
        ) {
            showToast('Host provisioning modal is unavailable', 'error');
            return;
        }
        if (provisionLabsLoading) {
            showToast('Lab associations are still loading', 'error');
            return;
        }
        const state = guacamoleCandidateState[provisionStationKey] || {};
        const labs = Array.isArray(state.labs) ? state.labs : [];
        const payload = {
            connectionId: provisionConnectionIdEl.value,
            name: provisionHostNameEl.value.trim(),
            address: provisionHostAddressEl.value.trim(),
            mac: provisionHostMacEl.value.trim(),
            labs,
            credentialRef: provisionHostAddressEl.value.trim(),
            heartbeatPath: provisionHeartbeatPathEl.value.trim(),
        };
        if (labs.length) payload.validLabIds = labs;
        await hostProvisioningController.save(payload, saveProvisionHostBtn);
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

    function handleHostActions(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const host = btn.closest('.host-row')?.dataset.host;
        if (!host) return;
        const action = btn.dataset.action;
        if (action === 'edit-host') {
            openEditHostModal(host);
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
        if (action === 'manage-winrm-trust') {
            openWinrmTrustModal(host);
            return;
        }
        if (action === 'sync-aas') {
            syncAasHost(host);
        }
    }

    async function toggleLocalMode(host, enabled) {
        return hostActionsController.toggleLocalMode(host, enabled);
    }

    async function triggerWol(host) {
        return hostActionsController.triggerWol(host);
    }

    async function triggerWinrm(host, command, args = []) {
        return hostActionsController.triggerWinrm(host, command, args);
    }

    async function syncAasHost(host) {
        return hostActionsController.syncAasHost(host);
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

    async function loadActionableReservations({ append = false, skipAuthPrompt = false } = {}) {
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
            const res = await fetch(`/lab-admin/reservations/actionable?${params.toString()}`, {
                credentials: 'include',
                ...(skipAuthPrompt ? { skipAuthPrompt: true } : {}),
            });
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
            const accessWindowEnded = isReservationWindowEnded(reservation);
            const displayedStatus = accessWindowEnded && !/access window ended/i.test(status)
                ? `${status} · ACCESS WINDOW ENDED`
                : status;
            const statusClass = accessWindowEnded
                ? 'warn'
                : numericStatus === 1 ? 'good' : numericStatus === 0 ? 'warn' : 'soft';
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
            const defaultReasonCode = reasonOptions[0]?.code;
            const actions = reservation.cancellable && reasonOptions.length
                ? `<div class="reservation-item-actions">
                    <button type="button" class="mini-btn danger" data-action="cancel-reservation" data-reservation-key="${escapeHtml(key)}">
                        ${cancellationButtonLabel(numericStatus, defaultReasonCode)}
                    </button>
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
                </div>`
                : `<div class="reservation-cancel-note">Cancellation unavailable for this status.</div>`;
            const renter = shortAddress(reservation.renter);
            const labLabel = resolveReservationLabDisplayName(reservation);
            const institution = reservation.institutionName || shortAddress(reservation.institutionAddress);
            return `<article class="reservation-item" data-reservation-key="${escapeHtml(key)}" data-reservation-status="${numericStatus ?? ''}">
                <div class="reservation-item-heading">
                    <span class="item-title">${escapeHtml(labLabel)}</span>
                    <span class="reservation-item-reference">Reservation: <code title="${escapeHtml(key)}">${escapeHtml(shortAddress(key, 12, 10))}</code></span>
                    <span class="pill ${statusClass}">${escapeHtml(displayedStatus)}</span>
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

    function isReservationWindowEnded(reservation) {
        const end = Number(reservation?.end);
        return Number.isFinite(end) && end > 0 && end <= Math.floor(Date.now() / 1000);
    }

    function normalizeReservationStatus(status) {
        const numericStatus = Number(status);
        return Number.isInteger(numericStatus) ? numericStatus : null;
    }

    function cancellationButtonLabel(status, reasonCode) {
        if (status === 0) return 'Decline request';
        if (status === 2 || reasonCode === 8) return 'Report service failure';
        return 'Cancel reservation';
    }

    function shortAddress(value, prefixLength = 6, suffixLength = 4) {
        const text = String(value || '');
        if (text.length <= prefixLength + suffixLength + 3) return text;
        return `${text.slice(0, prefixLength)}…${text.slice(-suffixLength)}`;
    }

    function handleUpcomingReservationReasonChange(event) {
        const reasonEl = event.target.closest('[data-reservation-reason]');
        if (!reasonEl || !upcomingReservationsListEl.contains(reasonEl)) return;
        const row = reasonEl.closest('.reservation-item');
        const button = row?.querySelector('[data-action="cancel-reservation"]');
        if (!button) return;
        const reservationStatus = normalizeReservationStatus(row.dataset.reservationStatus);
        button.textContent = cancellationButtonLabel(reservationStatus, Number(reasonEl.value));
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
        const confirmationMessage = reservationStatus === 2 || reasonCode === 8
            ? reservationStatus === 2
                ? 'Report provider service failure for this access-authorized reservation? The full price returns as service credits.'
                : 'Report provider service failure for this confirmed reservation? The full price returns as service credits.'
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
            showToast(
                reasonCode === 8
                    ? 'Provider service-failure report submitted'
                    : 'Reservation cancellation submitted',
                'success'
            );
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
            const labId = host.labId || reservation.labId;
            const labName = host.labName || reservation.labName;
            const rows = [
                { label: 'Reservation', value: reservation.reservationId || 'n/a', mono: true },
                { label: 'Lab', value: resolveReservationLabDisplayName({ labId, labName }) || 'n/a' },
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
