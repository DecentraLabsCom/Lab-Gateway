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
    const hostRenderersModule = window.LabManagerHostRenderers;
    if (!hostRenderersModule) {
        throw new Error('LabManagerHostRenderers must load before lab-manager.js');
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
    const winrmTrustModalModule = window.LabManagerWinrmTrustModal;
    if (!winrmTrustModalModule) {
        throw new Error('LabManagerWinrmTrustModal must load before lab-manager.js');
    }
    const hostProvisioningModule = window.LabManagerHostProvisioning;
    if (!hostProvisioningModule) {
        throw new Error('LabManagerHostProvisioning must load before lab-manager.js');
    }
    const hostModalsModule = window.LabManagerHostModals;
    if (!hostModalsModule) {
        throw new Error('LabManagerHostModals must load before lab-manager.js');
    }
    const opsAccessModule = window.LabManagerOpsAccess;
    if (!opsAccessModule) {
        throw new Error('LabManagerOpsAccess must load before lab-manager.js');
    }
    const hostViewModule = window.LabManagerHostView;
    if (!hostViewModule) {
        throw new Error('LabManagerHostView must load before lab-manager.js');
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
    const notificationsModule = window.LabManagerNotifications;
    if (!notificationsModule) {
        throw new Error('LabManagerNotifications must load before lab-manager.js');
    }
    const notificationsController = notificationsModule.createController({
        documentImpl: document,
        fetchImpl: (...args) => fetch(...args),
        showToast,
        getAuthTokenHandler: () => window.AuthTokenHandler,
        logger: console,
    });
    const requestNotificationsAccess = notificationsController.requestAccess;
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
    const reservationValuesModule = window.LabManagerReservationValues;
    if (!reservationValuesModule) {
        throw new Error('LabManagerReservationValues must load before lab-manager.js');
    }
    const reservationValuesController = reservationValuesModule.createController({
        dateTimeFormatCtor: Intl.DateTimeFormat,
        dateCtor: Date,
        formatDate,
        now: () => Date.now(),
    });
    const formatReservationDate = reservationValuesController.formatReservationDate;
    const formatRange = reservationValuesController.formatRange;
    const isReservationWindowEnded = reservationValuesController.isReservationWindowEnded;
    const normalizeReservationStatus = reservationValuesController.normalizeReservationStatus;
    const cancellationButtonLabel = reservationValuesController.cancellationButtonLabel;
    const shortAddress = reservationValuesController.shortAddress;
    const reservationRenderersModule = window.LabManagerReservationRenderers;
    if (!reservationRenderersModule) {
        throw new Error('LabManagerReservationRenderers must load before lab-manager.js');
    }
    const timelineModule = window.LabManagerTimeline;
    if (!timelineModule) {
        throw new Error('LabManagerTimeline must load before lab-manager.js');
    }
    const actionableReservationsModule = window.LabManagerActionableReservations;
    if (!actionableReservationsModule) {
        throw new Error('LabManagerActionableReservations must load before lab-manager.js');
    }
    const fmuSyncModule = window.LabManagerFmuSync;
    if (!fmuSyncModule) {
        throw new Error('LabManagerFmuSync must load before lab-manager.js');
    }
    const aasLinkModule = window.LabManagerAasLink;
    if (!aasLinkModule) {
        throw new Error('LabManagerAasLink must load before lab-manager.js');
    }
    const digitalTwinsModule = window.LabManagerDigitalTwins;
    if (!digitalTwinsModule) {
        throw new Error('LabManagerDigitalTwins must load before lab-manager.js');
    }
    const powerCredentialsModule = window.LabManagerPowerCredentials;
    if (!powerCredentialsModule) {
        throw new Error('LabManagerPowerCredentials must load before lab-manager.js');
    }
    const powerRenderersModule = window.LabManagerPowerRenderers;
    if (!powerRenderersModule) {
        throw new Error('LabManagerPowerRenderers must load before lab-manager.js');
    }
    const powerValuesModule = window.LabManagerPowerValues;
    if (!powerValuesModule) {
        throw new Error('LabManagerPowerValues must load before lab-manager.js');
    }
    const powerOperationsModule = window.LabManagerPowerOperations;
    if (!powerOperationsModule) {
        throw new Error('LabManagerPowerOperations must load before lab-manager.js');
    }
    const powerStatusModule = window.LabManagerPowerStatus;
    if (!powerStatusModule) {
        throw new Error('LabManagerPowerStatus must load before lab-manager.js');
    }
    const powerControllersModule = window.LabManagerPowerControllers;
    if (!powerControllersModule) {
        throw new Error('LabManagerPowerControllers must load before lab-manager.js');
    }
    const powerPoliciesModule = window.LabManagerPowerPolicies;
    if (!powerPoliciesModule) {
        throw new Error('LabManagerPowerPolicies must load before lab-manager.js');
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
    // Modal controls
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

    function openProvisionHostModal(stationKey) {
        return hostModalsController?.openProvision(stationKey);
    }

    function closeProvisionHostModal() {
        return hostModalsController?.closeProvision();
    }

    async function saveProvisionedHost() {
        return hostModalsController?.saveProvision();
    }

    function openEditHostModal(host) {
        return hostModalsController?.openEdit(host);
    }

    function closeEditHostModal() {
        return hostModalsController?.closeEdit();
    }

    async function saveEditedHost() {
        return hostModalsController?.saveEdit();
    }

    function openWinrmCredentialsModal(host) {
        return hostModalsController?.openCredentials(host);
    }

    function closeWinrmCredentialsModal() {
        return hostModalsController?.closeCredentials();
    }

    async function saveWinrmCredentials() {
        return hostModalsController?.saveCredentials();
    }
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
    notificationsController.initialize();

    // Lab Station ops state
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const opsHintEl = $('#opsHint');
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
    let winrmTrustModalController;
    let hostModalsController;
    let opsAccessController;
    let hostViewController;
    const guacamoleCandidateState = {};
    const heartbeatSources = {};
    const heartbeatStreamErrorShown = {};
    let powerControllersController;
    let powerPoliciesController;
    let digitalTwinsController;
    const powerValuesController = powerValuesModule.createController();
    const createPowerPolicyStepDraft = powerValuesController.createPowerPolicyStepDraft;
    const createPowerControllerOutletDraft = powerValuesController.createPowerControllerOutletDraft;
    const parsePowerPolicyInteger = powerValuesController.parsePowerPolicyInteger;
    const powerOperationsController = powerOperationsModule.createController();
    const buildPowerCommandPayload = powerOperationsController.buildPowerCommandPayload;
    const powerStatusController = powerStatusModule.createController();
    const mergePowerControllerStatuses = powerStatusController.mergePowerControllerStatuses;
    const powerRenderersController = powerRenderersModule.createController({ escapeHtml });
    let hostNames = [];

    const hostRenderersController = hostRenderersModule.createController({
        documentCtor: document,
        escapeHtml,
        formatDate,
        formatBool,
    });

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
            renderHosts: (...args) => hostViewController?.renderHosts(...args),
            loadActivityFeed,
            setGuacamoleCandidates: candidates => hostViewController?.setCandidates(candidates),
            renderGuacamoleCandidates: candidates => hostViewController?.renderCandidates(candidates),
            rememberGuacamoleCandidate: candidate => hostViewController?.rememberCandidate(candidate),
            groupGuacamoleCandidates: candidates => hostViewController?.groupCandidates(candidates) || [],
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
            renderCandidates: () => hostViewController?.renderCandidates(),
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
                if (winrmTrustModalController?.getState().activeHost === host) renderWinrmTrustState(trust);
            },
            onLoadError: (host, err) => {
                if (winrmTrustModalController?.getState().activeHost !== host) return;
                winrmTrustModalController.markUnavailable();
                updateWinrmTrustVerifyState();
                if (winrmTrustCurrentEl) {
                    winrmTrustCurrentEl.textContent = `Unable to load trust: ${err.message}`;
                }
                showToast(`WinRM trust status failed: ${err.message}`, 'error');
            },
            onPreview: preview => {
                renderWinrmTrustPreview(preview);
            },
            onReady: preview => {
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
    hostModalsController = hostModalsModule.createController({
        fields: {
            provisionModal: provisionHostModal,
            provisionSaveButton: saveProvisionHostBtn,
            provisionConnectionId: provisionConnectionIdEl,
            provisionHostName: provisionHostNameEl,
            provisionHostNameCandidates: provisionHostNameCandidatesEl,
            provisionHostAddress: provisionHostAddressEl,
            provisionHostMac: provisionHostMacEl,
            provisionHeartbeatPath: provisionHeartbeatPathEl,
            editModal: editHostModal,
            editOriginalName: editHostOriginalNameEl,
            editName: editHostNameEl,
            editAddress: editHostAddressEl,
            editMac: editHostMacEl,
            editHeartbeatPath: editHeartbeatPathEl,
            editSaveButton: saveEditHostBtn,
            credentialsModal: winrmCredentialsModal,
            credentialRef: winrmCredentialRefEl,
            credentialAddress: winrmCredentialAddressEl,
            credentialUser: winrmCredentialUserEl,
            credentialPassword: winrmCredentialPasswordEl,
            credentialSaveButton: saveWinrmCredentialsBtn,
        },
        hostMetadata,
        hostState,
        candidateState: guacamoleCandidateState,
        getStation: stationKey => hostViewController?.findStationCandidate(stationKey),
        fetchImpl: (...args) => fetch(...args),
        provisioningController: hostProvisioningController,
        credentialsController: winrmCredentialsController,
        callbacks: {
            showToast,
            loadHostInventory,
            stopHeartbeatStream,
        },
        documentImpl: document,
        logger: console,
    });
    hostViewController = hostViewModule.createController({
        hostListEl,
        candidateListEl: guacamoleCandidateListEl,
        getHostNames: () => hostNames,
        hostState,
        hostMetadata,
        candidateState: guacamoleCandidateState,
        hostRenderersController,
        documentImpl: document,
        windowImpl: window,
        callbacks: {
            onConfigureCandidate: openProvisionHostModal,
            onProbeCandidate: (...args) => hostDiscoveryController.probe(...args),
        },
    });
    winrmTrustModalController = winrmTrustModalModule.createController({
        fields: {
            modal: winrmTrustModal,
            modalHost: winrmTrustModalHostEl,
            current: winrmTrustCurrentEl,
            certificate: winrmTrustCertificateEl,
            certificateName: winrmTrustCertificateNameEl,
            preview: winrmTrustPreviewEl,
            previewDetails: winrmTrustPreviewDetailsEl,
            fingerprintConfirmed: winrmTrustFingerprintConfirmedEl,
            previewButton: previewWinrmTrustBtn,
            saveButton: saveWinrmTrustBtn,
            verifyButton: verifyWinrmTrustBtn,
            deleteButton: deleteWinrmTrustBtn,
        },
        hostMetadata,
        trustController: winrmTrustController,
        pollHeartbeat,
        formatDate,
        showToast,
        confirmImpl: message => window.confirm(message),
        documentImpl: document,
    });

    powerControllersController = powerControllersModule.createController({
        fields: {
            refresh: refreshPowerControllersBtn,
            list: powerControllerListEl,
            status: powerControllersStatusEl,
            hint: powerControllersHintEl,
            select: powerControllerSelectEl,
            id: powerControllerIdEl,
            name: powerControllerNameEl,
            driver: powerControllerDriverEl,
            enabled: powerControllerEnabledEl,
            host: powerControllerHostEl,
            port: powerControllerPortEl,
            credentialRef: powerControllerCredentialRefEl,
            netioPath: powerControllerNetioPathEl,
            netioHttps: powerControllerNetioHttpsEl,
            netioVerifyTls: powerControllerNetioVerifyTlsEl,
            netioPathField: powerControllerNetioPathFieldEl,
            netioHttpsField: powerControllerNetioHttpsFieldEl,
            netioVerifyTlsField: powerControllerNetioVerifyTlsFieldEl,
            profileField: powerControllerProfileFieldEl,
            profile: powerControllerProfileEl,
            timeoutSeconds: powerControllerTimeoutSecondsEl,
            retries: powerControllerRetriesEl,
            outlets: powerControllerOutletsEl,
            addOutlet: addPowerControllerOutletBtn,
            saveButton: savePowerControllerBtn,
            editorHint: powerControllerEditorHintEl,
            operationReason: powerOperationReasonEl,
            cycleSeconds: powerCycleSecondsEl,
            maintenanceMode: powerMaintenanceModeEl,
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
        showOpsWarning,
        renderPolicySteps: (...args) => powerPoliciesController?.renderSteps(...args),
        renderControllerRowsMarkup: (...args) => powerRenderersController.renderPowerControllerRowsMarkup(...args),
        renderControllerCredentialOptionsMarkup: (...args) => powerRenderersController.renderPowerControllerCredentialOptionsMarkup(...args),
        renderControllerOutletsMarkup: (...args) => powerRenderersController.renderPowerControllerOutletsMarkup(...args),
        mergePowerControllerStatuses,
        createPowerControllerOutletDraft,
        buildPowerCommandPayload,
        logger: console,
        documentImpl: document,
    });
    powerPoliciesController = powerPoliciesModule.createController({
        fields: {
            select: powerPolicySelectEl,
            labSelect: powerPolicyLabSelectEl,
            name: powerPolicyNameEl,
            enabled: powerPolicyEnabledEl,
            respectLocalMode: powerPolicyRespectLocalModeEl,
            maintenanceMode: powerPolicyMaintenanceModeEl,
            startFailureMode: powerPolicyStartFailureModeEl,
            endFailureMode: powerPolicyEndFailureModeEl,
            steps: powerPolicyStepsEl,
            addStep: addPowerPolicyStepBtn,
            saveButton: savePowerPolicyBtn,
            status: powerPoliciesStatusEl,
            editorHint: powerPolicyEditorHintEl,
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
        showOpsWarning,
        getControllers: () => powerControllersController?.getControllers() || [],
        getManagedLabs: () => digitalTwinsController?.getManagedLabs() || [],
        resolveLabDisplayName: lab => digitalTwinsController?.resolveLabDisplayName(lab) || '',
        renderPowerPolicyStepsMarkup: (...args) => powerRenderersController.renderPowerPolicyStepsMarkup(...args),
        createPowerPolicyStepDraft,
        parsePowerPolicyInteger,
        logger: console,
        documentImpl: document,
    });
    const loadPowerControllers = powerControllersController.load;
    const loadPowerControllerStatuses = powerControllersController.loadStatuses;
    const loadSelectedPowerController = powerControllersController.loadSelected;
    const savePowerController = powerControllersController.save;
    const updatePowerControllerDriverFields = powerControllersController.updateDriverFields;
    const updatePowerControllerNetioPort = powerControllersController.updateNetioPort;
    const suggestPowerControllerId = powerControllersController.suggestId;
    const addPowerControllerOutlet = powerControllersController.addOutlet;
    const handlePowerControllerOutletChange = powerControllersController.handleOutletChange;
    const handlePowerControllerOutletActions = powerControllersController.handleOutletActions;
    const handlePowerActions = powerControllersController.handleActions;
    const loadPowerPolicies = powerPoliciesController.load;
    const loadSelectedPowerPolicy = powerPoliciesController.loadSelected;
    const savePowerPolicy = powerPoliciesController.save;
    const handlePowerPolicyLabChange = powerPoliciesController.handleLabChange;
    const addPowerPolicyStep = powerPoliciesController.addStep;
    const handlePowerPolicyStepChange = powerPoliciesController.handleStepChange;
    const handlePowerPolicyStepActions = powerPoliciesController.handleStepActions;
    const resetPowerPolicyEditor = powerPoliciesController.resetEditor;

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
            powerControllersController.setCredentials(credentials);
        },
        escapeHtml,
        documentImpl: document,
    });
    const loadPowerCredentials = powerCredentialsController.load;
    powerCredentialsController.initialize();
    powerControllersController.initialize();
    powerPoliciesController.initialize();

    // Digital twins: managed labs, FMU sync and AAS links.
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
    const aasLinkKeyEl = $('#aasLinkKey');
    const aasLinkLabSelectEl = $('#aasLinkLabSelect');
    const aasLinkAasIdEl = $('#aasLinkAasId');
    const aasLinkSaveBtn = $('#aasLinkSaveBtn');
    const aasLinkCheckBtn = $('#aasLinkCheckBtn');
    const aasLinkDeleteBtn = $('#aasLinkDeleteBtn');
    const aasLinkResultEl = $('#aasLinkResult');
    digitalTwinsController = digitalTwinsModule.createController({
        fields: {
            powerPolicyLabSelect: powerPolicyLabSelectEl,
            powerPolicySelect: powerPolicySelectEl,
            fmuSyncKey: fmuSyncKeyEl,
            fmuSyncLabSelect: fmuSyncLabSelectEl,
            aasLinkLabSelect: aasLinkLabSelectEl,
            fmuSync: {
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
            aasLink: {
                keyInput: aasLinkKeyEl,
                labSelect: aasLinkLabSelectEl,
                aasIdInput: aasLinkAasIdEl,
                saveButton: aasLinkSaveBtn,
                checkButton: aasLinkCheckBtn,
                deleteButton: aasLinkDeleteBtn,
                result: aasLinkResultEl,
            },
        },
        fetchImpl: (...args) => fetch(...args),
        showToast,
        showOpsWarning,
        fmuSyncModule,
        aasLinkModule,
        formDataCtor: FormData,
        urlSearchParamsCtor: URLSearchParams,
        documentImpl: document,
        logger: console,
    });
    const getManagedLabs = digitalTwinsController.getManagedLabs;
    const loadManagedLabsOnce = digitalTwinsController.loadManagedLabsOnce;
    digitalTwinsController.initialize();

    // Reservation timeline elements
    const timelineInput = $('#timelineReservationId');
    const timelineBtn = $('#loadTimelineBtn');
    const timelineResult = $('#timelineResult');
    const upcomingReservationsListEl = $('#upcomingReservationsList');
    const upcomingReservationsStatusEl = $('#upcomingReservationsStatus');
    opsAccessController = opsAccessModule.createController({
        opsHintEl,
        refreshHostsBtn,
        timelineBtn,
        fetchImpl: (...args) => fetch(...args),
        groupCandidates: candidates => hostViewController?.groupCandidates(candidates) || [],
        logger: console,
    });
    const reservationRenderersController = reservationRenderersModule.createController({
        escapeHtml,
        htmlEscape,
        formatDate,
        formatBool,
        formatReservationDate,
        formatRange,
        isReservationWindowEnded,
        normalizeReservationStatus,
        cancellationButtonLabel,
        shortAddress,
        resolveReservationLabDisplayName,
    });
    const timelineController = timelineModule.createController({
        timelineInput,
        timelineBtn,
        timelineResult,
        fetchImpl: (...args) => fetch(...args),
        normalizePagination,
        renderTimelineMarkup: (...args) => reservationRenderersController.renderTimelineMarkup(...args),
        showToast,
        logger: console,
    });
    timelineController.bind();
    const actionableReservationsController = actionableReservationsModule.createController({
        listEl: upcomingReservationsListEl,
        statusEl: upcomingReservationsStatusEl,
        fetchImpl: (...args) => fetch(...args),
        renderMarkup: (...args) => reservationRenderersController.renderUpcomingReservationsMarkup(...args),
        escapeHtml,
        normalizeReservationStatus,
        cancellationButtonLabel,
        showToast,
        confirmImpl: message => window.confirm(message),
        logger: console,
    });
    const loadActionableReservations = actionableReservationsController.load;
    actionableReservationsController.bind();

    if (refreshHostsBtn) {
        refreshHostsBtn.addEventListener('click', refreshAllHosts);
    }
    if (hostListEl) {
        hostListEl.addEventListener('click', handleHostActions);
        hostViewController?.renderHosts();
    }
    if (refreshPowerCredentialsBtn) refreshPowerCredentialsBtn.addEventListener('click', loadPowerCredentials);
    hostViewController?.bind();

    document.addEventListener('lab-manager:tab-activated', event => {
        initializeManagerTab(event.detail && event.detail.tab);
    });
    if (window.LabManagerTabs && window.LabManagerTabs.activeTab) {
        initializeManagerTab(window.LabManagerTabs.activeTab);
    }

    async function refreshLabManagerSession() {
        return opsAccessController ? opsAccessController.refreshSession() : false;
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

    function $(sel) { return document.querySelector(sel); }

    // ---- Lab Station ops helpers ----
    function updateOpsHint(data) {
        return opsAccessController?.updateHint(data);
    }

    function resolveReservationLabDisplayName(reservation) {
        const directName = [reservation?.labName, reservation?.name]
            .find(candidate => typeof candidate === 'string' && candidate.trim());
        if (directName) return directName.trim();
        const managedLab = getManagedLabs().find(lab => String(lab?.labId ?? '') === String(reservation?.labId ?? ''));
        return digitalTwinsController.resolveLabDisplayName(managedLab || reservation);
    }

    function winrmTrustErrorMessage(body, status) {
        const code = String(body?.code || '').trim();
        const requestSuffix = body?.requestId ? ` (request ID ${body.requestId})` : '';
        return `${body?.error || `HTTP ${status}`}${code ? ` [${code}]` : ''}${requestSuffix}`;
    }

    function renderWinrmTrustState(trust) {
        return winrmTrustModalController?.renderState(trust);
    }

    function renderWinrmTrustPreview(preview) {
        return winrmTrustModalController?.renderPreview(preview);
    }

    function updateWinrmTrustVerifyState() {
        return winrmTrustModalController?.updateVerifyState();
    }

    function updateWinrmTrustSaveState() {
        return winrmTrustModalController?.updateSaveState();
    }

    function handleWinrmTrustCertificateSelected() {
        return winrmTrustModalController?.handleCertificateSelected();
    }

    async function openWinrmTrustModal(host) {
        return winrmTrustModalController?.open(host);
    }

    async function loadWinrmTrustState(host) {
        return winrmTrustModalController?.load(host);
    }

    function closeWinrmTrustModal() {
        return winrmTrustModalController?.close();
    }

    async function previewWinrmTrust() {
        return winrmTrustModalController?.preview();
    }

    async function saveWinrmTrust() {
        return winrmTrustModalController?.save();
    }

    async function verifyWinrmTrust() {
        return winrmTrustModalController?.verify();
    }

    async function deleteWinrmTrust() {
        return winrmTrustModalController?.delete();
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

    async function checkOpsAvailability() {
        return opsAccessController ? opsAccessController.checkAvailability() : false;
    }

    function showOpsWarning() {
        return opsAccessController?.showWarning();
    }});
