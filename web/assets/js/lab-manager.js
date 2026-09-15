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
    let guacamoleCandidates = [];
    let guacamoleStationCandidates = [];
    let provisionStationKey = '';
    let provisionLabsLoading = false;

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
        renderHosts();
    }
    if (refreshPowerCredentialsBtn) refreshPowerCredentialsBtn.addEventListener('click', loadPowerCredentials);
    if (guacamoleCandidateListEl) {
        guacamoleCandidateListEl.addEventListener('click', handleGuacamoleCandidateActions);
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

    function resolveReservationLabDisplayName(reservation) {
        const directName = [reservation?.labName, reservation?.name]
            .find(candidate => typeof candidate === 'string' && candidate.trim());
        if (directName) return directName.trim();
        const managedLab = getManagedLabs().find(lab => String(lab?.labId ?? '') === String(reservation?.labId ?? ''));
        return digitalTwinsController.resolveLabDisplayName(managedLab || reservation);
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
        const row = hostRenderersController.buildHostRow(
            host,
            hostState[host] || {},
            hostMetadata[host] || {},
        );
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
        return hostRenderersController.buildGuacamoleCandidateRow(
            station,
            guacamoleCandidateState,
        );
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
