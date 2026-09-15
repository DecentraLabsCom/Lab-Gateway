(function (root) {
    'use strict';

    function requireModule(module, name) {
        if (!module) throw new Error(`${name} must load before the host feature`);
        return module;
    }

    function createController({
        documentImpl = root.document,
        windowImpl = root,
        fetchImpl,
        formDataCtor = root.FormData,
        formatDate,
        formatBool,
        escapeHtml,
        formatHeartbeatStreamError,
        isHeartbeatConfigurationError,
        loadActivityFeed,
        updateOpsHint,
        showOpsWarning,
        showToast,
        confirmImpl = message => windowImpl.confirm?.(message),
        logger = console,
    }) {
        const hostsModule = requireModule(root.LabManagerHosts, 'LabManagerHosts');
        const hostRenderersModule = requireModule(root.LabManagerHostRenderers, 'LabManagerHostRenderers');
        const hostDiscoveryModule = requireModule(root.LabManagerHostDiscovery, 'LabManagerHostDiscovery');
        const winrmCredentialsModule = requireModule(root.LabManagerWinrmCredentials, 'LabManagerWinrmCredentials');
        const winrmTrustModule = requireModule(root.LabManagerWinrmTrust, 'LabManagerWinrmTrust');
        const winrmTrustModalModule = requireModule(root.LabManagerWinrmTrustModal, 'LabManagerWinrmTrustModal');
        const hostProvisioningModule = requireModule(root.LabManagerHostProvisioning, 'LabManagerHostProvisioning');
        const hostModalsModule = requireModule(root.LabManagerHostModals, 'LabManagerHostModals');
        const hostViewModule = requireModule(root.LabManagerHostView, 'LabManagerHostView');
        const hostActionBindingsModule = requireModule(root.LabManagerHostActionBindings, 'LabManagerHostActionBindings');
        const hostActionsModule = requireModule(root.LabManagerHostActions, 'LabManagerHostActions');
        const modalBindingsModule = requireModule(root.LabManagerModalBindings, 'LabManagerModalBindings');
        const $ = selector => documentImpl?.querySelector?.(selector) || null;

        const refreshHostsButton = $('#refreshHostsBtn');
        const hostListElement = $('#hostList');
        const opsHintElement = $('#opsHint');
        const candidateListElement = $('#guacamoleCandidateList');
        const provisionHostModal = $('#provisionHostModal');
        const closeProvisionHostModalButton = $('#closeProvisionHostModal');
        const cancelProvisionHostButton = $('#cancelProvisionHost');
        const saveProvisionHostButton = $('#saveProvisionHost');
        const winrmCredentialsModal = $('#winrmCredentialsModal');
        const closeWinrmCredentialsModalButton = $('#closeWinrmCredentialsModal');
        const cancelWinrmCredentialsButton = $('#cancelWinrmCredentials');
        const saveWinrmCredentialsButton = $('#saveWinrmCredentials');
        const winrmTrustModal = $('#winrmTrustModal');
        const closeWinrmTrustModalButton = $('#closeWinrmTrustModal');
        const cancelWinrmTrustButton = $('#cancelWinrmTrust');
        const previewWinrmTrustButton = $('#previewWinrmTrust');
        const saveWinrmTrustButton = $('#saveWinrmTrust');
        const verifyWinrmTrustButton = $('#verifyWinrmTrust');
        const deleteWinrmTrustButton = $('#deleteWinrmTrust');
        const winrmTrustModalHost = $('#winrmTrustModalHost');
        const winrmTrustCurrent = $('#winrmTrustCurrent');
        const winrmTrustCertificate = $('#winrmTrustCertificate');
        const winrmTrustCertificateName = $('#winrmTrustCertificateName');
        const winrmTrustPreview = $('#winrmTrustPreview');
        const winrmTrustPreviewDetails = $('#winrmTrustPreviewDetails');
        const winrmTrustFingerprintConfirmed = $('#winrmTrustFingerprintConfirmed');
        const editHostModal = $('#editHostModal');
        const closeEditHostModalButton = $('#closeEditHostModal');
        const cancelEditHostButton = $('#cancelEditHost');
        const saveEditHostButton = $('#saveEditHost');
        const winrmCredentialRef = $('#winrmCredentialRef');
        const winrmCredentialAddress = $('#winrmCredentialAddress');
        const winrmCredentialUser = $('#winrmCredentialUser');
        const winrmCredentialPassword = $('#winrmCredentialPassword');
        const provisionConnectionId = $('#provisionConnectionId');
        const provisionHostName = $('#provisionHostName');
        const provisionHostNameCandidates = $('#provisionHostNameCandidates');
        const provisionHostAddress = $('#provisionHostAddress');
        const provisionHostMac = $('#provisionHostMac');
        const provisionHeartbeatPath = $('#provisionHeartbeatPath');
        const editHostOriginalName = $('#editHostOriginalName');
        const editHostName = $('#editHostName');
        const editHostAddress = $('#editHostAddress');
        const editHostMac = $('#editHostMac');
        const editHeartbeatPath = $('#editHeartbeatPath');

        const hostState = {};
        const hostMetadata = {};
        const candidateState = {};
        const heartbeatSources = {};
        const heartbeatStreamErrorShown = {};
        let hostNames = [];
        let hostModalsController;
        let hostViewController;
        let winrmTrustModalController;

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

        const hostRenderersController = hostRenderersModule.createController({
            documentCtor: documentImpl,
            escapeHtml,
            formatDate,
            formatBool,
        });
        const hostsController = hostsModule.createController({
            fetchImpl,
            getEventSource: () => windowImpl.EventSource,
            getOrigin: () => windowImpl.location.origin,
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
            logger,
        });
        const loadHostInventory = hostsController.loadInventory;
        const startHeartbeatStream = hostsController.startHeartbeatStream;
        const stopHeartbeatStream = hostsController.stopHeartbeatStream;
        const refreshAllHosts = hostsController.refreshAllHosts;
        const pollHeartbeat = hostsController.pollHeartbeat;
        const hostActionsController = hostActionsModule.createController({
            fetchImpl,
            callbacks: {
                pollHeartbeat,
                showToast,
            },
            logger,
        });
        const hostActionBindingsController = hostActionBindingsModule.createController({
            hostListEl: hostListElement,
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
            fetchImpl,
            candidateState,
            callbacks: {
                renderCandidates: () => hostViewController?.renderCandidates(),
                loadHostInventory,
                showToast,
            },
            logger,
        });
        const winrmCredentialsController = winrmCredentialsModule.createController({
            fetchImpl,
            callbacks: {
                closeModal: closeWinrmCredentialsModal,
                loadHostInventory,
                showToast,
            },
            logger,
        });
        const winrmTrustController = winrmTrustModule.createController({
            fetchImpl,
            formDataCtor,
            formatErrorMessage: winrmTrustErrorMessage,
            callbacks: {
                onLoaded: (host, trust) => {
                    if (winrmTrustModalController?.getState().activeHost === host) renderWinrmTrustState(trust);
                },
                onLoadError: (host, err) => {
                    if (winrmTrustModalController?.getState().activeHost !== host) return;
                    winrmTrustModalController.markUnavailable();
                    updateWinrmTrustVerifyState();
                    if (winrmTrustCurrent) winrmTrustCurrent.textContent = `Unable to load trust: ${err.message}`;
                    showToast(`WinRM trust status failed: ${err.message}`, 'error');
                },
                onPreview: preview => renderWinrmTrustPreview(preview),
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
                    if (deleteWinrmTrustButton) deleteWinrmTrustButton.disabled = false;
                },
            },
        });
        const hostProvisioningController = hostProvisioningModule.createController({
            fetchImpl,
            callbacks: {
                closeModal: closeProvisionHostModal,
                loadHostInventory,
                showToast,
            },
            logger,
        });
        hostModalsController = hostModalsModule.createController({
            fields: {
                provisionModal: provisionHostModal,
                provisionSaveButton: saveProvisionHostButton,
                provisionConnectionId,
                provisionHostName,
                provisionHostNameCandidates,
                provisionHostAddress,
                provisionHostMac,
                provisionHeartbeatPath,
                editModal: editHostModal,
                editOriginalName: editHostOriginalName,
                editName: editHostName,
                editAddress: editHostAddress,
                editMac: editHostMac,
                editHeartbeatPath,
                editSaveButton: saveEditHostButton,
                credentialsModal: winrmCredentialsModal,
                credentialRef: winrmCredentialRef,
                credentialAddress: winrmCredentialAddress,
                credentialUser: winrmCredentialUser,
                credentialPassword: winrmCredentialPassword,
                credentialSaveButton: saveWinrmCredentialsButton,
            },
            hostMetadata,
            hostState,
            candidateState,
            getStation: stationKey => hostViewController?.findStationCandidate(stationKey),
            fetchImpl,
            provisioningController: hostProvisioningController,
            credentialsController: winrmCredentialsController,
            callbacks: {
                showToast,
                loadHostInventory,
                stopHeartbeatStream,
            },
            documentImpl,
            logger,
        });
        hostViewController = hostViewModule.createController({
            hostListEl: hostListElement,
            candidateListEl: candidateListElement,
            getHostNames: () => hostNames,
            hostState,
            hostMetadata,
            candidateState,
            hostRenderersController,
            documentImpl,
            windowImpl,
            callbacks: {
                onConfigureCandidate: openProvisionHostModal,
                onProbeCandidate: (...args) => hostDiscoveryController.probe(...args),
            },
        });
        winrmTrustModalController = winrmTrustModalModule.createController({
            fields: {
                modal: winrmTrustModal,
                modalHost: winrmTrustModalHost,
                current: winrmTrustCurrent,
                certificate: winrmTrustCertificate,
                certificateName: winrmTrustCertificateName,
                preview: winrmTrustPreview,
                previewDetails: winrmTrustPreviewDetails,
                fingerprintConfirmed: winrmTrustFingerprintConfirmed,
                previewButton: previewWinrmTrustButton,
                saveButton: saveWinrmTrustButton,
                verifyButton: verifyWinrmTrustButton,
                deleteButton: deleteWinrmTrustButton,
            },
            hostMetadata,
            trustController: winrmTrustController,
            pollHeartbeat,
            formatDate,
            showToast,
            confirmImpl,
            documentImpl,
        });
        const modalBindingsController = modalBindingsModule.createController({
            fields: {
                closeProvision: closeProvisionHostModalButton,
                cancelProvision: cancelProvisionHostButton,
                saveProvision: saveProvisionHostButton,
                closeCredentials: closeWinrmCredentialsModalButton,
                cancelCredentials: cancelWinrmCredentialsButton,
                saveCredentials: saveWinrmCredentialsButton,
                closeTrust: closeWinrmTrustModalButton,
                cancelTrust: cancelWinrmTrustButton,
                previewTrust: previewWinrmTrustButton,
                saveTrust: saveWinrmTrustButton,
                verifyTrust: verifyWinrmTrustButton,
                deleteTrust: deleteWinrmTrustButton,
                trustCertificate: winrmTrustCertificate,
                trustFingerprint: winrmTrustFingerprintConfirmed,
                closeEdit: closeEditHostModalButton,
                cancelEdit: cancelEditHostButton,
                saveEdit: saveEditHostButton,
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

        function initialize() {
            modalBindingsController.bind();
        }

        function bind() {
            if (refreshHostsButton) refreshHostsButton.addEventListener('click', refreshAllHosts);
            hostActionBindingsController.bind();
            if (hostListElement) hostViewController?.renderHosts();
            hostViewController?.bind();
        }

        return Object.freeze({
            groupCandidates: candidates => hostViewController?.groupCandidates(candidates) || [],
            hasHostList: () => Boolean(hostListElement),
            initialize,
            bind,
            loadHostInventory,
            pollHeartbeat,
            refreshAllHosts,
            refreshHostsButton,
            startHeartbeatStream,
            stopHeartbeatStream,
            hostListElement,
            opsHintElement,
            openWinrmTrustModal,
            loadWinrmTrustState,
        });
    }

    root.LabManagerHostFeature = Object.freeze({ createController });
})(window);
