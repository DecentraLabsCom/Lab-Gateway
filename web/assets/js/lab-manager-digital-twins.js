(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        showOpsWarning,
        fmuSyncModule = root.LabManagerFmuSync,
        aasLinkModule = root.LabManagerAasLink,
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

        let managedLabsInitialized = false;
        let managedLabsPromise = null;
        let managedLabs = [];
        let fmuSyncController = null;
        let aasLinkController = null;

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
                const option = documentImpl.createElement('option');
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
            const selectEl = fields.fmuSyncKey;
            if (!selectEl) return;
            const current = selectEl.value;
            const accessKeys = (Array.isArray(labs) ? labs : [])
                .filter(lab => Number(lab?.resourceType) === 1)
                .filter(lab => String(lab?.accessKey || '').trim())
                .filter((lab, index, items) => items.findIndex(item => String(item.accessKey) === String(lab.accessKey)) === index);
            selectEl.innerHTML = accessKeys.length
                ? '<option value="">Select an FMU access key</option>'
                : '<option value="">No FMU access keys available</option>';
            accessKeys.forEach(lab => {
                const accessKey = String(lab.accessKey).trim();
                const option = documentImpl.createElement('option');
                option.value = accessKey;
                option.textContent = `${resolveLabDisplayName(lab)} · ${accessKey}`;
                selectEl.appendChild(option);
            });
            const selected = preferredAccessKey || current || '';
            selectEl.value = accessKeys.some(lab => String(lab.accessKey) === selected)
                ? selected
                : '';
            selectEl.disabled = accessKeys.length === 0;
        }

        function clearManagedLabs() {
            managedLabs = [];
            renderPowerPolicyLabOptions([]);
            renderFmuAccessKeyOptions([]);
            renderFmuLabOptions(fields.fmuSyncLabSelect, []);
            renderFmuLabOptions(fields.aasLinkLabSelect, []);
        }

        async function loadManagedLabs(options = {}) {
            if (
                !fields.powerPolicyLabSelect
                && !fields.fmuSyncKey
                && !fields.fmuSyncLabSelect
                && !fields.aasLinkLabSelect
            ) return;
            const selectedPowerPolicyLabId = fields.powerPolicyLabSelect?.value || '';
            const selectedFmuAccessKey = fields.fmuSyncKey?.value || '';
            const selectedFmuLabId = fields.fmuSyncLabSelect?.value || '';
            const selectedAasLinkLabId = fields.aasLinkLabSelect?.value || '';
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
                renderPowerPolicyLabOptions(managedLabs, selectedPowerPolicyLabId);
                renderFmuAccessKeyOptions(managedLabs, selectedFmuAccessKey);
                renderFmuLabOptions(fields.fmuSyncLabSelect, managedLabs, selectedFmuLabId);
                renderFmuLabOptions(fields.aasLinkLabSelect, managedLabs, selectedAasLinkLabId);
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
        }

        return Object.freeze({
            clearManagedLabs,
            formatPowerPolicyLabLabel,
            getManagedLabs: () => managedLabs,
            initialize,
            loadManagedLabs,
            loadManagedLabsOnce,
            renderFmuAccessKeyOptions,
            renderFmuLabOptions,
            renderPowerPolicyLabOptions,
            resolveLabDisplayName,
        });
    }

    root.LabManagerDigitalTwins = Object.freeze({ createController });
})(window);
