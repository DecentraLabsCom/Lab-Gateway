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
    const hostActionBindingsModule = window.LabManagerHostActionBindings;
    if (!hostActionBindingsModule) {
        throw new Error('LabManagerHostActionBindings must load before lab-manager.js');
    }
    const operationsLifecycleModule = window.LabManagerOperationsLifecycle;
    if (!operationsLifecycleModule) {
        throw new Error('LabManagerOperationsLifecycle must load before lab-manager.js');
    }
    const modalBindingsModule = window.LabManagerModalBindings;
    if (!modalBindingsModule) {
        throw new Error('LabManagerModalBindings must load before lab-manager.js');
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
    const reservationsFeatureModule = window.LabManagerReservationsFeature;
    if (!reservationsFeatureModule) {
        throw new Error('LabManagerReservationsFeature must load before lab-manager.js');
    }
    const energyFeatureModule = window.LabManagerEnergyFeature;
    if (!energyFeatureModule) {
        throw new Error('LabManagerEnergyFeature must load before lab-manager.js');
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
    loadAccessPolicy();
    notificationsController.initialize();

    // Lab Station ops state
    const refreshHostsBtn = $('#refreshHostsBtn');
    const hostListEl = $('#hostList');
    const opsHintEl = $('#opsHint');
    const guacamoleCandidateListEl = $('#guacamoleCandidateList');
    const hostState = {};
    const hostMetadata = {};
    let winrmTrustModalController;
    let hostModalsController;
    let opsAccessController;
    let hostViewController;
    const guacamoleCandidateState = {};
    const heartbeatSources = {};
    const heartbeatStreamErrorShown = {};
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
    const hostActionBindingsController = hostActionBindingsModule.createController({
        hostListEl,
        hostState,
        callbacks: {
            onEditHost: openEditHostModal,
            onPoll: pollHeartbeat,
            onWakeOnLan: host => hostActionsController.triggerWol(host),
            onWinrm: (...args) => hostActionsController.triggerWinrm(...args),
            onToggleLocalMode: (...args) => hostActionsController.toggleLocalMode(...args),
            onCredentials: openWinrmCredentialsModal,
            onTrust: openWinrmTrustModal,
            onSyncAas: host => hostActionsController.syncAasHost(host),
        },
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
    const modalBindingsController = modalBindingsModule.createController({
        fields: {
            closeProvision: closeProvisionHostModalBtn,
            cancelProvision: cancelProvisionHostBtn,
            saveProvision: saveProvisionHostBtn,
            closeCredentials: closeWinrmCredentialsModalBtn,
            cancelCredentials: cancelWinrmCredentialsBtn,
            saveCredentials: saveWinrmCredentialsBtn,
            closeTrust: closeWinrmTrustModalBtn,
            cancelTrust: cancelWinrmTrustBtn,
            previewTrust: previewWinrmTrustBtn,
            saveTrust: saveWinrmTrustBtn,
            verifyTrust: verifyWinrmTrustBtn,
            deleteTrust: deleteWinrmTrustBtn,
            trustCertificate: winrmTrustCertificateEl,
            trustFingerprint: winrmTrustFingerprintConfirmedEl,
            closeEdit: closeEditHostModalBtn,
            cancelEdit: cancelEditHostBtn,
            saveEdit: saveEditHostBtn,
        },
        callbacks: {
            closeProvision: closeProvisionHostModal,
            saveProvision: saveProvisionedHost,
            closeCredentials: closeWinrmCredentialsModal,
            saveCredentials: saveWinrmCredentials,
            closeTrust: closeWinrmTrustModal,
            previewTrust: previewWinrmTrust,
            saveTrust: saveWinrmTrust,
            verifyTrust: verifyWinrmTrust,
            deleteTrust: deleteWinrmTrust,
            trustCertificateSelected: handleWinrmTrustCertificateSelected,
            trustFingerprintChanged: updateWinrmTrustSaveState,
            closeEdit: closeEditHostModal,
            saveEdit: saveEditedHost,
        },
    });
    modalBindingsController.bind();

    const energyFeatureController = energyFeatureModule.createController({
        documentImpl: document,
        fetchImpl: (...args) => fetch(...args),
        showToast,
        showOpsWarning,
        escapeHtml,
        formDataCtor: FormData,
        urlSearchParamsCtor: URLSearchParams,
        logger: console,
    });
    energyFeatureController.initialize();

    const reservationsFeatureController = reservationsFeatureModule.createController({
        documentImpl: document,
        fetchImpl: (...args) => fetch(...args),
        normalizePagination,
        escapeHtml,
        htmlEscape,
        formatDate,
        formatBool,
        showToast,
        getManagedLabs: (...args) => energyFeatureController.getManagedLabs(...args),
        resolveLabDisplayName: (...args) => energyFeatureController.resolveLabDisplayName(...args),
        confirmImpl: message => window.confirm(message),
        dateTimeFormatCtor: Intl.DateTimeFormat,
        dateCtor: Date,
        now: () => Date.now(),
        logger: console,
    });
    reservationsFeatureController.initialize();

    opsAccessController = opsAccessModule.createController({
        opsHintEl,
        refreshHostsBtn,
        timelineBtn: reservationsFeatureController.timelineButton,
        fetchImpl: (...args) => fetch(...args),
        groupCandidates: candidates => hostViewController?.groupCandidates(candidates) || [],
        logger: console,
    });
    const operationsLifecycleController = operationsLifecycleModule.createController({
        hasHostList: Boolean(hostListEl),
        hasReservationList: reservationsFeatureController.hasReservationList(),
        refreshSession: () => opsAccessController?.refreshSession(),
        loadManagedLabs: (...args) => energyFeatureController.loadManagedLabsOnce(...args),
        checkAvailability: (...args) => checkOpsAvailability(...args),
        loadHostInventory: (...args) => loadHostInventory(...args),
        loadActionableReservations: (...args) => reservationsFeatureController.loadActionableReservations(...args),
        loadActivityFeed: (...args) => loadActivityFeed(...args),
    });

    if (refreshHostsBtn) {
        refreshHostsBtn.addEventListener('click', refreshAllHosts);
    }
    hostActionBindingsController.bind();
    if (hostListEl) hostViewController?.renderHosts();
    hostViewController?.bind();

    document.addEventListener('lab-manager:tab-activated', event => {
        initializeManagerTab(event.detail && event.detail.tab);
    });
    if (window.LabManagerTabs && window.LabManagerTabs.activeTab) {
        initializeManagerTab(window.LabManagerTabs.activeTab);
    }

    function initializeManagerTab(tabName) {
        if (!managerState.claimTab(tabName)) return;

        if (tabName === 'operations') {
            void operationsLifecycleController.initialize();
            return;
        }
        if (tabName === 'energy') {
            energyFeatureController.initializeTab(tabName);
            return;
        }
        if (tabName === 'digital-twins') {
            energyFeatureController.initializeTab(tabName);
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
    async function checkOpsAvailability() {
        return opsAccessController ? opsAccessController.checkAvailability() : false;
    }

    function showOpsWarning() {
        return opsAccessController?.showWarning();
    }});
