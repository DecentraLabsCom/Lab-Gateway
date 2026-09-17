(function (root) {
    'use strict';

    function createController({
        fields = {},
        hostMetadata = {},
        hostState = {},
        candidateState = {},
        getStation = () => null,
        fetchImpl,
        provisioningController,
        credentialsController,
        callbacks = {},
        documentImpl = root.document,
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHostModals requires fetchImpl');
        }
        if (!provisioningController || typeof provisioningController.save !== 'function') {
            throw new Error('LabManagerHostModals requires provisioningController');
        }
        if (!credentialsController || typeof credentialsController.save !== 'function') {
            throw new Error('LabManagerHostModals requires credentialsController');
        }
        if (!documentImpl || typeof documentImpl.createElement !== 'function') {
            throw new Error('LabManagerHostModals requires documentImpl');
        }

        const {
            showToast = () => {},
            loadHostInventory = async () => {},
            stopHeartbeatStream = () => {},
        } = callbacks;
        let provisionStationKey = '';
        function renderProvisionNameCandidates(candidates) {
            const target = fields.provisionHostNameCandidates;
            if (!target) return;
            target.innerHTML = '';
            const seen = new Set();
            (Array.isArray(candidates) ? candidates : []).forEach(candidate => {
                const value = (candidate || '').toString().trim();
                if (!value || seen.has(value)) return;
                seen.add(value);
                const option = documentImpl.createElement('option');
                option.value = value;
                target.appendChild(option);
            });
        }

        function openProvision(stationKey) {
            const station = getStation(stationKey);
            const provision = fields;
            if (
                !station ||
                !provision.provisionModal ||
                !provision.provisionConnectionId ||
                !provision.provisionHostName ||
                !provision.provisionHostAddress ||
                !provision.provisionHostMac ||
                !provision.provisionHostBroadcast ||
                !provision.provisionHeartbeatPath
            ) {
                showToast('Host provisioning modal is unavailable', 'error');
                return;
            }
            const representative = station.connections[0];
            const state = candidateState[stationKey] || {};
            const draft = state.opsHostDraft || {};
            const host = station.address || station.nameCandidates[0] || '';
            provisionStationKey = stationKey;
            provision.provisionConnectionId.value = String(state.connectionId || representative?.id || '');
            provision.provisionHostName.value = draft.name || host;
            renderProvisionNameCandidates(draft.nameCandidates || station.nameCandidates);
            provision.provisionHostAddress.value = draft.address || station.address || '';
            provision.provisionHostMac.value = draft.mac || '';
            provision.provisionHostBroadcast.value = draft.broadcast || '';
            provision.provisionHeartbeatPath.value = draft.heartbeat_path
                || 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json';
            provision.provisionModal.classList.add('show');
        }

        function closeProvision() {
            if (fields.provisionModal) fields.provisionModal.classList.remove('show');
        }

        async function saveProvision() {
            const provision = fields;
            if (
                !provision.provisionConnectionId ||
                !provision.provisionHostName ||
                !provision.provisionHostAddress ||
                !provision.provisionHostMac ||
                !provision.provisionHostBroadcast ||
                !provision.provisionHeartbeatPath
            ) {
                showToast('Host provisioning modal is unavailable', 'error');
                return;
            }
            const payload = {
                connectionId: provision.provisionConnectionId.value,
                name: provision.provisionHostName.value.trim(),
                address: provision.provisionHostAddress.value.trim(),
                mac: provision.provisionHostMac.value.trim(),
                broadcast: provision.provisionHostBroadcast.value.trim(),
                credentialRef: provision.provisionHostAddress.value.trim(),
                heartbeatPath: provision.provisionHeartbeatPath.value.trim(),
            };
            await provisioningController.save(payload, provision.provisionSaveButton);
        }

        function openEdit(host) {
            const meta = hostMetadata[host] || {};
            const edit = fields;
            if (
                !meta.editable ||
                !edit.editModal ||
                !edit.editOriginalName ||
                !edit.editName ||
                !edit.editAddress ||
                !edit.editMac ||
                !edit.editBroadcast ||
                !edit.editHeartbeatPath
            ) {
                showToast('Only dynamically configured hosts can be edited', 'error');
                return;
            }
            edit.editOriginalName.value = host;
            edit.editName.value = meta.name || host;
            edit.editAddress.value = meta.address || host;
            edit.editMac.value = meta.mac || '';
            edit.editBroadcast.value = meta.broadcast || '';
            edit.editHeartbeatPath.value = meta.heartbeatPath
                || 'C:\\LabStation\\labstation\\data\\telemetry\\heartbeat.json';
            edit.editModal.classList.add('show');
        }

        function closeEdit() {
            if (fields.editModal) fields.editModal.classList.remove('show');
        }

        async function saveEdit() {
            const edit = fields;
            if (!edit.editOriginalName || !edit.editName || !edit.editMac || !edit.editBroadcast || !edit.editHeartbeatPath) {
                showToast('Host edit modal is unavailable', 'error');
                return;
            }
            const originalName = edit.editOriginalName.value.trim();
            const payload = {
                name: edit.editName.value.trim(),
                mac: edit.editMac.value.trim(),
                broadcast: edit.editBroadcast.value.trim(),
                heartbeatPath: edit.editHeartbeatPath.value.trim(),
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
            if (edit.editSaveButton) edit.editSaveButton.disabled = true;
            try {
                const res = await fetchImpl(`/ops/api/hosts/${encodeURIComponent(originalName)}`, {
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
                closeEdit();
                showToast(`Ops host ${body.host?.name || payload.name} updated`, 'success');
                await loadHostInventory({ skipAuthPrompt: true });
            } catch (err) {
                logger.error(err);
                showToast(`Edit host failed: ${err.message}`, 'error');
            } finally {
                if (edit.editSaveButton) edit.editSaveButton.disabled = false;
            }
        }

        function openCredentials(host) {
            const meta = hostMetadata[host] || {};
            const credentialRef = meta.credentialRef || meta.address || host;
            const credentials = fields;
            if (
                !credentials.credentialsModal ||
                !credentials.credentialRef ||
                !credentials.credentialAddress ||
                !credentials.credentialUser ||
                !credentials.credentialPassword
            ) {
                showToast('WinRM credentials modal is unavailable', 'error');
                return;
            }
            credentials.credentialRef.value = credentialRef;
            credentials.credentialAddress.value = meta.address || credentialRef;
            credentials.credentialUser.value = '.\\LabGatewaySvc';
            credentials.credentialPassword.value = '';
            credentials.credentialsModal.classList.add('show');
        }

        function closeCredentials() {
            if (fields.credentialsModal) fields.credentialsModal.classList.remove('show');
        }

        async function saveCredentials() {
            const credentials = fields;
            if (!credentials.credentialRef || !credentials.credentialUser || !credentials.credentialPassword) {
                showToast('WinRM credentials modal is unavailable', 'error');
                return;
            }
            const payload = {
                credentialRef: credentials.credentialRef.value.trim(),
                user: credentials.credentialUser.value.trim(),
                password: credentials.credentialPassword.value,
            };
            await credentialsController.save(payload, credentials.credentialSaveButton);
        }

        function getState() {
            return { provisionStationKey };
        }

        return Object.freeze({
            closeCredentials,
            closeEdit,
            closeProvision,
            getState,
            openCredentials,
            openEdit,
            openProvision,
            saveCredentials,
            saveEdit,
            saveProvision,
        });
    }

    root.LabManagerHostModals = Object.freeze({ createController });
})(window);
