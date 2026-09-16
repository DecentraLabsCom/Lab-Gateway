(function (root) {
    'use strict';

    function requireModule(module, name) {
        if (!module) throw new Error(`${name} must load before the energy feature`);
        return module;
    }

    function createController({
        documentImpl = root.document,
        fetchImpl,
        showToast,
        showOpsWarning,
        escapeHtml,
        formDataCtor = root.FormData,
        urlSearchParamsCtor = root.URLSearchParams,
        logger = console,
    }) {
        const fmuSyncModule = requireModule(root.LabManagerFmuSync, 'LabManagerFmuSync');
        const aasLinkModule = requireModule(root.LabManagerAasLink, 'LabManagerAasLink');
        const digitalTwinsModule = requireModule(root.LabManagerDigitalTwins, 'LabManagerDigitalTwins');
        const powerCredentialsModule = requireModule(root.LabManagerPowerCredentials, 'LabManagerPowerCredentials');
        const powerRenderersModule = requireModule(root.LabManagerPowerRenderers, 'LabManagerPowerRenderers');
        const powerValuesModule = requireModule(root.LabManagerPowerValues, 'LabManagerPowerValues');
        const powerOperationsModule = requireModule(root.LabManagerPowerOperations, 'LabManagerPowerOperations');
        const powerStatusModule = requireModule(root.LabManagerPowerStatus, 'LabManagerPowerStatus');
        const powerControllersModule = requireModule(root.LabManagerPowerControllers, 'LabManagerPowerControllers');
        const powerPoliciesModule = requireModule(root.LabManagerPowerPolicies, 'LabManagerPowerPolicies');
        const $ = selector => documentImpl?.querySelector?.(selector) || null;

        const fields = {
            refreshPowerControllers: $('#refreshPowerControllersBtn'),
            powerControllerList: $('#powerControllerList'),
            powerControllersStatus: $('#powerControllersStatus'),
            powerControllersHint: $('#powerControllersHint'),
            powerControllerSelect: $('#powerControllerSelect'),
            powerControllerId: $('#powerControllerId'),
            powerControllerName: $('#powerControllerName'),
            powerControllerDriver: $('#powerControllerDriver'),
            powerControllerEnabled: $('#powerControllerEnabled'),
            powerControllerHost: $('#powerControllerHost'),
            powerControllerPort: $('#powerControllerPort'),
            powerControllerCredentialRef: $('#powerControllerCredentialRef'),
            powerControllerNetioPath: $('#powerControllerNetioPath'),
            powerControllerNetioHttps: $('#powerControllerNetioHttps'),
            powerControllerNetioVerifyTls: $('#powerControllerNetioVerifyTls'),
            powerControllerNetioPathField: $('#powerControllerNetioPathField'),
            powerControllerNetioHttpsField: $('#powerControllerNetioHttpsField'),
            powerControllerNetioVerifyTlsField: $('#powerControllerNetioVerifyTlsField'),
            powerControllerProfileField: $('#powerControllerProfileField'),
            powerControllerProfile: $('#powerControllerProfile'),
            powerControllerTimeoutSeconds: $('#powerControllerTimeoutSeconds'),
            powerControllerRetries: $('#powerControllerRetries'),
            powerControllerOutlets: $('#powerControllerOutlets'),
            addPowerControllerOutlet: $('#addPowerControllerOutletBtn'),
            savePowerController: $('#savePowerControllerBtn'),
            powerControllerEditorHint: $('#powerControllerEditorHint'),
            powerOperationReason: $('#powerOperationReason'),
            powerCycleSeconds: $('#powerCycleSeconds'),
            powerMaintenanceMode: $('#powerMaintenanceMode'),
            refreshPowerCredentials: $('#refreshPowerCredentialsBtn'),
            powerCredentialsList: $('#powerCredentialsList'),
            powerCredentialsStatus: $('#powerCredentialsStatus'),
            powerCredentialsHint: $('#powerCredentialsHint'),
            powerCredentialSelect: $('#powerCredentialSelect'),
            powerCredentialRef: $('#powerCredentialRef'),
            powerCredentialType: $('#powerCredentialType'),
            powerCredentialUsername: $('#powerCredentialUsername'),
            powerCredentialPassword: $('#powerCredentialPassword'),
            powerCredentialCommunity: $('#powerCredentialCommunity'),
            powerCredentialAuthProtocol: $('#powerCredentialAuthProtocol'),
            powerCredentialAuthPassword: $('#powerCredentialAuthPassword'),
            powerCredentialPrivProtocol: $('#powerCredentialPrivProtocol'),
            powerCredentialPrivPassword: $('#powerCredentialPrivPassword'),
            powerCredentialContextName: $('#powerCredentialContextName'),
            powerCredentialUsernameField: $('#powerCredentialUsernameField'),
            powerCredentialPasswordField: $('#powerCredentialPasswordField'),
            powerCredentialCommunityField: $('#powerCredentialCommunityField'),
            powerCredentialAuthProtocolField: $('#powerCredentialAuthProtocolField'),
            powerCredentialAuthPasswordField: $('#powerCredentialAuthPasswordField'),
            powerCredentialPrivProtocolField: $('#powerCredentialPrivProtocolField'),
            powerCredentialPrivPasswordField: $('#powerCredentialPrivPasswordField'),
            powerCredentialContextNameField: $('#powerCredentialContextNameField'),
            powerCredentialSave: $('#powerCredentialSaveBtn'),
            powerCredentialEditorHint: $('#powerCredentialEditorHint'),
            powerPolicySelect: $('#powerPolicySelect'),
            powerPolicyLabSelect: $('#powerPolicyLabSelect'),
            powerPolicyName: $('#powerPolicyName'),
            powerPolicyEnabled: $('#powerPolicyEnabled'),
            powerPolicyRespectLocalMode: $('#powerPolicyRespectLocalMode'),
            powerPolicyMaintenanceMode: $('#powerPolicyMaintenanceMode'),
            powerPolicyStartFailureMode: $('#powerPolicyStartFailureMode'),
            powerPolicyEndFailureMode: $('#powerPolicyEndFailureMode'),
            powerPolicySteps: $('#powerPolicySteps'),
            addPowerPolicyStep: $('#addPowerPolicyStepBtn'),
            savePowerPolicy: $('#savePowerPolicyBtn'),
            powerPoliciesStatus: $('#powerPoliciesStatus'),
            powerPolicyEditorHint: $('#powerPolicyEditorHint'),
            fmuSync: {
                syncButton: $('#fmuSyncBtn'),
                keyInput: $('#fmuSyncKey'),
                fileInput: $('#fmuSyncFile'),
                fileName: $('#fmuSyncFileName'),
                contactEmail: $('#fmuSyncContactEmail'),
            },
            aasLink: {
                keyInput: $('#aasLinkKey'),
                aasIdInput: $('#aasLinkAasId'),
                saveButton: $('#aasLinkSaveBtn'),
                checkButton: $('#aasLinkCheckBtn'),
                deleteButton: $('#aasLinkDeleteBtn'),
            },
        };

        const powerValuesController = powerValuesModule.createController();
        const powerOperationsController = powerOperationsModule.createController();
        const powerStatusController = powerStatusModule.createController();
        const powerRenderersController = powerRenderersModule.createController({ escapeHtml });
        let powerPoliciesController;
        let digitalTwinsController;

        const powerControllersController = powerControllersModule.createController({
            fields: {
                refresh: fields.refreshPowerControllers,
                list: fields.powerControllerList,
                status: fields.powerControllersStatus,
                hint: fields.powerControllersHint,
                select: fields.powerControllerSelect,
                id: fields.powerControllerId,
                name: fields.powerControllerName,
                driver: fields.powerControllerDriver,
                enabled: fields.powerControllerEnabled,
                host: fields.powerControllerHost,
                port: fields.powerControllerPort,
                credentialRef: fields.powerControllerCredentialRef,
                netioPath: fields.powerControllerNetioPath,
                netioHttps: fields.powerControllerNetioHttps,
                netioVerifyTls: fields.powerControllerNetioVerifyTls,
                netioPathField: fields.powerControllerNetioPathField,
                netioHttpsField: fields.powerControllerNetioHttpsField,
                netioVerifyTlsField: fields.powerControllerNetioVerifyTlsField,
                profileField: fields.powerControllerProfileField,
                profile: fields.powerControllerProfile,
                timeoutSeconds: fields.powerControllerTimeoutSeconds,
                retries: fields.powerControllerRetries,
                outlets: fields.powerControllerOutlets,
                addOutlet: fields.addPowerControllerOutlet,
                saveButton: fields.savePowerController,
                editorHint: fields.powerControllerEditorHint,
                operationReason: fields.powerOperationReason,
                cycleSeconds: fields.powerCycleSeconds,
                maintenanceMode: fields.powerMaintenanceMode,
            },
            fetchImpl,
            showToast,
            showOpsWarning,
            renderPolicySteps: (...args) => powerPoliciesController?.renderSteps(...args),
            renderControllerRowsMarkup: (...args) => powerRenderersController.renderPowerControllerRowsMarkup(...args),
            renderControllerCredentialOptionsMarkup: (...args) => powerRenderersController.renderPowerControllerCredentialOptionsMarkup(...args),
            renderControllerOutletsMarkup: (...args) => powerRenderersController.renderPowerControllerOutletsMarkup(...args),
            mergePowerControllerStatuses: powerStatusController.mergePowerControllerStatuses,
            createPowerControllerOutletDraft: powerValuesController.createPowerControllerOutletDraft,
            buildPowerCommandPayload: powerOperationsController.buildPowerCommandPayload,
            logger,
            documentImpl,
        });

        powerPoliciesController = powerPoliciesModule.createController({
            fields: {
                select: fields.powerPolicySelect,
                labSelect: fields.powerPolicyLabSelect,
                name: fields.powerPolicyName,
                enabled: fields.powerPolicyEnabled,
                respectLocalMode: fields.powerPolicyRespectLocalMode,
                maintenanceMode: fields.powerPolicyMaintenanceMode,
                startFailureMode: fields.powerPolicyStartFailureMode,
                endFailureMode: fields.powerPolicyEndFailureMode,
                steps: fields.powerPolicySteps,
                addStep: fields.addPowerPolicyStep,
                saveButton: fields.savePowerPolicy,
                status: fields.powerPoliciesStatus,
                editorHint: fields.powerPolicyEditorHint,
            },
            fetchImpl,
            showToast,
            showOpsWarning,
            getControllers: () => powerControllersController.getControllers() || [],
            getManagedLabs: () => digitalTwinsController?.getManagedLabs() || [],
            resolveLabDisplayName: lab => digitalTwinsController?.resolveLabDisplayName(lab) || '',
            renderPowerPolicyStepsMarkup: (...args) => powerRenderersController.renderPowerPolicyStepsMarkup(...args),
            createPowerPolicyStepDraft: powerValuesController.createPowerPolicyStepDraft,
            parsePowerPolicyInteger: powerValuesController.parsePowerPolicyInteger,
            logger,
            documentImpl,
        });

        const powerCredentialsController = powerCredentialsModule.createController({
            fields: {
                select: fields.powerCredentialSelect,
                ref: fields.powerCredentialRef,
                type: fields.powerCredentialType,
                username: fields.powerCredentialUsername,
                password: fields.powerCredentialPassword,
                community: fields.powerCredentialCommunity,
                authProtocol: fields.powerCredentialAuthProtocol,
                authPassword: fields.powerCredentialAuthPassword,
                privProtocol: fields.powerCredentialPrivProtocol,
                privPassword: fields.powerCredentialPrivPassword,
                contextName: fields.powerCredentialContextName,
                usernameField: fields.powerCredentialUsernameField,
                passwordField: fields.powerCredentialPasswordField,
                communityField: fields.powerCredentialCommunityField,
                authProtocolField: fields.powerCredentialAuthProtocolField,
                authPasswordField: fields.powerCredentialAuthPasswordField,
                privProtocolField: fields.powerCredentialPrivProtocolField,
                privPasswordField: fields.powerCredentialPrivPasswordField,
                contextNameField: fields.powerCredentialContextNameField,
                saveButton: fields.powerCredentialSave,
                list: fields.powerCredentialsList,
                status: fields.powerCredentialsStatus,
                hint: fields.powerCredentialsHint,
                editorHint: fields.powerCredentialEditorHint,
            },
            fetchImpl,
            showToast,
            showOpsWarning,
            refreshPowerControllerStatuses: (...args) => powerControllersController.loadStatuses(...args),
            renderControllerCredentialOptions: credentials => powerControllersController.setCredentials(credentials),
            escapeHtml,
            documentImpl,
        });

        digitalTwinsController = digitalTwinsModule.createController({
            fields: {
                powerPolicyLabSelect: fields.powerPolicyLabSelect,
                powerPolicySelect: fields.powerPolicySelect,
                fmuSyncKey: fields.fmuSync.keyInput,
                aasLinkKey: fields.aasLink.keyInput,
                fmuSync: fields.fmuSync,
                aasLink: fields.aasLink,
            },
            fetchImpl,
            showToast,
            showOpsWarning,
            fmuSyncModule,
            aasLinkModule,
            formDataCtor,
            urlSearchParamsCtor,
            documentImpl,
            logger,
        });

        const loadPowerControllers = powerControllersController.load;
        const loadPowerCredentials = powerCredentialsController.load;
        const loadPowerPolicies = powerPoliciesController.load;
        const getManagedLabs = digitalTwinsController.getManagedLabs;
        const loadManagedLabsOnce = digitalTwinsController.loadManagedLabsOnce;

        function initialize() {
            powerCredentialsController.initialize();
            powerControllersController.initialize();
            powerPoliciesController.initialize();
            digitalTwinsController.initialize();
            fields.refreshPowerCredentials?.addEventListener('click', () => loadPowerCredentials({
                notifySuccess: true,
                notifyError: true,
            }));
        }

        function loadPowerPoliciesAfterManagedLabs(options = {}) {
            const managedLabsLoad = fields.powerPolicyLabSelect
                ? loadManagedLabsOnce()
                : Promise.resolve();
            void managedLabsLoad.then(
                () => loadPowerPolicies(options),
                () => loadPowerPolicies(options),
            );
        }

        function hasEnergyTab() {
            return Boolean(
                fields.powerControllerList
                || fields.powerControllerSelect
                || fields.powerCredentialsList
                || fields.powerCredentialSelect
                || fields.powerPolicyLabSelect
                || fields.powerPolicySelect
            );
        }

        function hasDigitalTwinsTab() {
            return Boolean(fields.fmuSync.keyInput || fields.aasLink.keyInput);
        }

        function initializeTab(tabName) {
            if (tabName === 'energy') {
                if (fields.powerControllerList || fields.powerControllerSelect) loadPowerControllers({ skipAuthPrompt: true });
                if (fields.powerCredentialsList || fields.powerCredentialSelect) loadPowerCredentials({ skipAuthPrompt: true });
                if (fields.powerPolicySelect) loadPowerPoliciesAfterManagedLabs({ skipAuthPrompt: true });
                else if (fields.powerPolicyLabSelect) loadManagedLabsOnce();
                return;
            }
            if (tabName === 'digital-twins' && hasDigitalTwinsTab()) loadManagedLabsOnce();
        }

        return Object.freeze({
            getManagedLabs,
            hasDigitalTwinsTab,
            hasEnergyTab,
            initialize,
            initializeTab,
            loadManagedLabsOnce,
            resolveLabDisplayName: digitalTwinsController.resolveLabDisplayName,
        });
    }

    root.LabManagerEnergyFeature = Object.freeze({ createController });
})(window);
