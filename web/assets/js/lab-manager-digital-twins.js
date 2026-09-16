(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        showOpsWarning,
        escapeHtml,
        fmuSyncModule = root.LabManagerFmuSync,
        aasLinkModule = root.LabManagerAasLink,
        aasxModule = root.LabManagerAasx,
        formDataCtor = root.FormData,
        urlSearchParamsCtor = root.URLSearchParams,
        documentImpl = typeof document === 'undefined' ? root.document : document,
        logger = console,
    }) {
        if (!fmuSyncModule) {
            throw new Error('LabManagerFmuSync must load before the digital-twins controller');
        }
        if (!aasLinkModule) {
            throw new Error('LabManagerAasLink must load before the digital-twins controller');
        }
        if (!aasxModule) {
            throw new Error('LabManagerAasx must load before the digital-twins controller');
        }

        let managedLabsInitialized = false;
        let managedLabsPromise = null;
        let managedLabs = [];
        let physicalLabIdsWithRegisteredConnection = new Set();
        let fmuSyncController = null;
        let aasLinkController = null;
        let aasxController = null;

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

        function resolveLabDescription(lab) {
            const candidates = [
                lab?.description,
                lab?.metadataDescription,
                lab?.metadata?.description,
            ];
            const description = candidates.find(candidate => typeof candidate === 'string' && candidate.trim());
            return description ? description.trim() : '';
        }

        function resolveLabDocumentation(lab) {
            const candidates = [
                lab?.documentation,
                lab?.docs,
                lab?.metadataDocumentation,
                lab?.metadata?.documentation,
                lab?.metadata?.docs,
            ];
            const documentation = candidates.flatMap(value => (
                Array.isArray(value) ? value : typeof value === 'string' ? [value] : []
            ));
            return [...new Set(documentation.map(value => String(value).trim()).filter(Boolean))];
        }

        function resolveLabLicense(lab) {
            const termsOfUse = lab?.termsOfUse ?? lab?.metadata?.termsOfUse;
            if (typeof termsOfUse === 'string') return termsOfUse.trim();
            const url = termsOfUse?.url ?? termsOfUse?.href;
            return typeof url === 'string' ? url.trim() : '';
        }

        function formatPowerPolicyLabLabel(lab) {
            const resourceType = Number(lab?.resourceType) === 1 ? 'FMU' : 'Remote';
            const status = lab?.listed ? 'Listed' : 'Draft';
            return `${resolveLabDisplayName(lab)} · ${resourceType} · ${status}`;
        }

        function renderPowerPolicyLabOptions(labs, preferredLabId = '') {
            const selectEl = fields.powerPolicyLabSelect;
            if (!selectEl) return;
            const current = selectEl.value;
            const validLabs = (Array.isArray(labs) ? labs : [])
                .filter(lab => String(lab?.labId || '').trim())
                .filter((lab, index, items) => items.findIndex(item => String(item.labId) === String(lab.labId)) === index);
            selectEl.innerHTML = validLabs.length
                ? '<option value="">Select a laboratory</option>'
                : '<option value="">No laboratories available</option>';
            validLabs.forEach(lab => {
                const labId = String(lab.labId).trim();
                const option = documentImpl.createElement('option');
                option.value = labId;
                option.textContent = formatPowerPolicyLabLabel(lab);
                selectEl.appendChild(option);
            });
            const selected = preferredLabId || current || fields.powerPolicySelect?.value || '';
            selectEl.value = validLabs.some(lab => String(lab.labId) === selected)
                ? selected
                : '';
            selectEl.disabled = validLabs.length === 0;
        }

        function formatDigitalTwinLabLabel(lab) {
            const resourceType = Number(lab?.resourceType) === 1
                ? 'FMU'
                : 'Physical laboratory';
            const status = lab?.listed ? 'Listed' : 'Draft';
            return `${resolveLabDisplayName(lab)} · ${resourceType} · ${status}`;
        }

        function renderDigitalTwinLaboratoryOptions(selectEl, labs, preferredLabId = '') {
            if (!selectEl) return;
            const current = selectEl.value;
            const validLabs = (Array.isArray(labs) ? labs : [])
                .filter(lab => String(lab?.labId || '').trim())
                .filter((lab, index, items) => items.findIndex(item => String(item.labId) === String(lab.labId)) === index);
            selectEl.innerHTML = validLabs.length
                ? '<option value="">Select a laboratory</option>'
                : '<option value="">No laboratories available</option>';
            validLabs.forEach(lab => {
                const labId = String(lab.labId).trim();
                const option = documentImpl.createElement('option');
                option.value = labId;
                option.dataset.labId = labId;
                option.dataset.accessKey = String(lab.accessKey || '').trim();
                option.dataset.resourceType = Number(lab.resourceType) === 1 ? '1' : '0';
                option.dataset.labDescription = resolveLabDescription(lab);
                option.dataset.labDocumentation = JSON.stringify(resolveLabDocumentation(lab));
                option.dataset.labLicense = resolveLabLicense(lab);
                option.textContent = formatDigitalTwinLabLabel(lab);
                selectEl.appendChild(option);
            });
            const selected = preferredLabId || current || '';
            selectEl.value = validLabs.some(lab => String(lab.labId) === selected)
                ? selected
                : '';
            selectEl.disabled = validLabs.length === 0;
        }

        function resolveLabId(lab) {
            return String(lab?.labId || '').trim();
        }

        function isPhysicalLaboratory(lab) {
            return Number(lab?.resourceType) !== 1;
        }

        function digitalTwinLaboratories(labs) {
            return (Array.isArray(labs) ? labs : []).filter(lab => (
                !isPhysicalLaboratory(lab)
                || physicalLabIdsWithRegisteredConnection.has(resolveLabId(lab))
            ));
        }

        async function loadLabAssociations(options = {}) {
            physicalLabIdsWithRegisteredConnection = new Set();

            try {
                const res = await fetchImpl('/ops/api/lab-associations', options);
                if (res.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (res.status === 401) {
                    if (!options.skipAuthPrompt) {
                        showToast('Lab Manager session required to load laboratory associations', 'error');
                    }
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const body = await res.json().catch(() => ({}));
                (Array.isArray(body.associations) ? body.associations : []).forEach(association => {
                    const labId = String(association?.labId || '').trim();
                    if (labId) physicalLabIdsWithRegisteredConnection.add(labId);
                });
            } catch (error) {
                logger.warn('Unable to load calculated laboratory associations', error);
            }
        }

        function clearManagedLabs() {
            managedLabs = [];
            physicalLabIdsWithRegisteredConnection = new Set();
            renderPowerPolicyLabOptions([]);
            renderDigitalTwinLaboratoryOptions(fields.fmuSyncKey, []);
            renderDigitalTwinLaboratoryOptions(fields.aasLinkKey, []);
            aasxController?.clearPackages();
        }

        async function loadManagedLabs(options = {}) {
            if (
                !fields.powerPolicyLabSelect
                && !fields.fmuSyncKey
                && !fields.aasLinkKey
                && !fields.aasx?.packageList
            ) return;
            const selectedPowerPolicyLabId = fields.powerPolicyLabSelect?.value || '';
            const selectedFmuLabId = fields.fmuSyncKey?.value || '';
            const selectedAasLinkLabId = fields.aasLinkKey?.value || '';
            try {
                const res = await fetchImpl('/lab-admin/labs', options);
                if (res.status === 403) {
                    showOpsWarning();
                    clearManagedLabs();
                    return;
                }
                if (res.status === 401) {
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load laboratories', 'error');
                    clearManagedLabs();
                    return;
                }
                const body = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
                managedLabs = Array.isArray(body.labs) ? body.labs : [];
                await loadLabAssociations(options);
                const digitalTwinLabs = digitalTwinLaboratories(managedLabs);
                aasxController?.setManagedLabs(managedLabs);
                renderPowerPolicyLabOptions(managedLabs, selectedPowerPolicyLabId);
                renderDigitalTwinLaboratoryOptions(fields.fmuSyncKey, digitalTwinLabs, selectedFmuLabId);
                renderDigitalTwinLaboratoryOptions(fields.aasLinkKey, digitalTwinLabs, selectedAasLinkLabId);
                if (aasxController) await aasxController.loadPackages(options);
            } catch (error) {
                logger.warn('Unable to load provider laboratories', error);
                clearManagedLabs();
            }
        }

        function loadManagedLabsOnce(options = {}) {
            if (managedLabsPromise) return managedLabsPromise;
            if (managedLabsInitialized) return Promise.resolve();
            managedLabsInitialized = true;
            managedLabsPromise = loadManagedLabs(options);
            return managedLabsPromise;
        }

        function initialize() {
            if (fmuSyncController || aasLinkController) return;
            fmuSyncController = fmuSyncModule.createController({
                fields: fields.fmuSync,
                fetchImpl,
                showToast,
                formDataCtor,
                urlSearchParamsCtor,
                logger,
            });
            fmuSyncController.initialize();
            aasLinkController = aasLinkModule.createController({
                fields: fields.aasLink,
                fetchImpl,
                showToast,
            });
            aasLinkController.initialize();
            aasxController = aasxModule.createController({
                fields: fields.aasx,
                fetchImpl,
                showToast,
                escapeHtml,
                resolveLabDisplayName,
                logger,
            });
            aasxController.initialize();
        }

        return Object.freeze({
            clearManagedLabs,
            formatPowerPolicyLabLabel,
            getManagedLabs: () => managedLabs,
            initialize,
            loadManagedLabs,
            loadManagedLabsOnce,
            formatDigitalTwinLabLabel,
            renderDigitalTwinLaboratoryOptions,
            renderPowerPolicyLabOptions,
            resolveLabDisplayName,
            resolveLabDocumentation,
            resolveLabLicense,
        });
    }

    root.LabManagerDigitalTwins = Object.freeze({ createController });
})(window);
