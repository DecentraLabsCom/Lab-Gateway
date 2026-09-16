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
    const hostFeatureModule = window.LabManagerHostFeature;
    if (!hostFeatureModule) {
        throw new Error('LabManagerHostFeature must load before lab-manager.js');
    }
    const opsAccessModule = window.LabManagerOpsAccess;
    if (!opsAccessModule) {
        throw new Error('LabManagerOpsAccess must load before lab-manager.js');
    }
    const operationsLifecycleModule = window.LabManagerOperationsLifecycle;
    if (!operationsLifecycleModule) {
        throw new Error('LabManagerOperationsLifecycle must load before lab-manager.js');
    }
    const toastModule = window.LabManagerToast;
    if (!toastModule) {
        throw new Error('LabManagerToast must load before lab-manager.js');
    }
    const toastController = toastModule.getDefaultController({
        document,
        setTimeoutImpl: setTimeout,
    });
    const showToast = toastController.showToast;
    const notificationsFeatureModule = window.LabManagerNotificationsFeature;
    if (!notificationsFeatureModule) {
        throw new Error('LabManagerNotificationsFeature must load before lab-manager.js');
    }
    const notificationsFeatureController = notificationsFeatureModule.createController({
        documentImpl: document,
        fetchImpl: (...args) => fetch(...args),
        showToast,
        getAuthTokenHandler: () => window.AuthTokenHandler,
        logger: console,
    });
    const requestNotificationsAccess = notificationsFeatureController.requestAccess;
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
        showToast,
        logger: console,
    });
    const loadActivityFeed = activityFeedController.loadActivityFeed;
    loadAccessPolicy();
    notificationsFeatureController.initialize();

    let opsAccessController;
    const hostFeatureController = hostFeatureModule.createController({
        documentImpl: document,
        windowImpl: window,
        fetchImpl: (...args) => fetch(...args),
        formDataCtor: FormData,
        formatDate,
        formatBool,
        escapeHtml,
        formatHeartbeatStreamError,
        isHeartbeatConfigurationError,
        loadActivityFeed,
        updateOpsHint,
        showOpsWarning,
        showToast,
        confirmImpl: message => window.confirm(message),
        logger: console,
    });
    hostFeatureController.initialize();
    const refreshHostsBtn = hostFeatureController.refreshHostsButton;
    const opsHintEl = hostFeatureController.opsHintElement;

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
        groupCandidates: candidates => hostFeatureController.groupCandidates(candidates),
        logger: console,
    });
    const operationsLifecycleController = operationsLifecycleModule.createController({
        hasHostList: hostFeatureController.hasHostList(),
        hasReservationList: reservationsFeatureController.hasReservationList(),
        refreshSession: () => opsAccessController?.refreshSession(),
        loadManagedLabs: (...args) => energyFeatureController.loadManagedLabsOnce(...args),
        checkAvailability: (...args) => checkOpsAvailability(...args),
        loadHostInventory: (...args) => hostFeatureController.loadHostInventory(...args),
        loadActionableReservations: (...args) => reservationsFeatureController.loadActionableReservations(...args),
        loadActivityFeed: (...args) => loadActivityFeed(...args),
    });

    hostFeatureController.bind();

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

    async function checkOpsAvailability() {
        return opsAccessController ? opsAccessController.checkAvailability() : false;
    }

    function showOpsWarning() {
        return opsAccessController?.showWarning();
    }});
