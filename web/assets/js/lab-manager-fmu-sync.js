(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        formDataCtor = root.FormData,
        urlSearchParamsCtor = root.URLSearchParams,
        encodeURIComponentImpl = encodeURIComponent,
        logger = console,
    }) {
        let descriptionAutoFilled = false;
        let licenseAutoFilled = false;

        function setFmuFieldFromHint(inputEl, hintEl, value) {
            if (!inputEl) return;
            inputEl.value = value;
            inputEl.readOnly = true;
            inputEl.style.opacity = '0.7';
            inputEl.style.cursor = 'default';
            if (hintEl) {
                hintEl.textContent = '\u2139\ufe0f From FMU';
                hintEl.hidden = false;
            }
        }

        function clearFmuFieldHint(inputEl, hintEl) {
            if (!inputEl) return;
            inputEl.readOnly = false;
            inputEl.style.opacity = '';
            inputEl.style.cursor = '';
            if (hintEl) {
                hintEl.textContent = '';
                hintEl.hidden = true;
            }
        }

        function clearAllFmuHints() {
            if (descriptionAutoFilled) {
                clearFmuFieldHint(fields.description, fields.descriptionHint);
                if (fields.description) fields.description.value = '';
                descriptionAutoFilled = false;
            }
            if (licenseAutoFilled) {
                clearFmuFieldHint(fields.license, fields.licenseHint);
                if (fields.license) fields.license.value = '';
                licenseAutoFilled = false;
            }
        }

        async function fetchFmuHints(accessKey) {
            if (!accessKey) {
                clearAllFmuHints();
                return;
            }
            try {
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/hints`);
                if (!response.ok) {
                    clearAllFmuHints();
                    return;
                }
                const hints = await response.json();
                if (hints.description && fields.description && !fields.description.value.trim()) {
                    setFmuFieldFromHint(fields.description, fields.descriptionHint, hints.description);
                    descriptionAutoFilled = true;
                }
                if (hints.license && fields.license && !fields.license.value.trim()) {
                    setFmuFieldFromHint(fields.license, fields.licenseHint, hints.license);
                    licenseAutoFilled = true;
                }
            } catch (_error) {
                // FMU hints are best-effort and must not block the sync form.
            }
        }

        async function syncAasFmu(accessKey, labId, aasxFile, extraInfo = {}) {
            if (!accessKey) {
                showToast('Enter a FMU access key', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            if (fields.result) fields.result.textContent = '';
            try {
                let response;
                const url = `/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/sync`;
                if (aasxFile) {
                    const form = new formDataCtor();
                    form.append('file', aasxFile);
                    if (labId) form.append('labId', labId);
                    if (extraInfo.description) form.append('description', extraInfo.description);
                    if (extraInfo.license) form.append('license', extraInfo.license);
                    if (extraInfo.docsUrl) form.append('documentationUrl', extraInfo.docsUrl);
                    if (extraInfo.contactEmail) form.append('contactEmail', extraInfo.contactEmail);
                    response = await fetchImpl(url, { method: 'POST', body: form });
                } else {
                    const params = new urlSearchParamsCtor();
                    if (labId) params.set('labId', labId);
                    if (extraInfo.description) params.set('description', extraInfo.description);
                    if (extraInfo.license) params.set('license', extraInfo.license);
                    if (extraInfo.docsUrl) params.set('documentationUrl', extraInfo.docsUrl);
                    if (extraInfo.contactEmail) params.set('contactEmail', extraInfo.contactEmail);
                    const query = params.toString() ? `?${params.toString()}` : '';
                    response = await fetchImpl(url + query, { method: 'POST' });
                }
                if (response.status === 403) {
                    showToast('AAS admin unavailable in Lite mode or blocked by gateway policy', 'error');
                    return;
                }
                if (response.status === 401) {
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                if (!response.ok) {
                    const body = await response.json().catch(() => ({}));
                    throw new Error(body.detail || `HTTP ${response.status}`);
                }
                const data = await response.json();
                if (fields.result) {
                    const message = data.aasxUpload
                        ? `Synced ${(data.uploadedAasIds || []).length} shell(s) + ${(data.uploadedSubmodelIds || []).length} submodel(s) from AASX`
                        : `AAS shell synced \u2014 ${data.created ? 'created' : 'updated'}`;
                    fields.result.textContent = message;
                    fields.result.style.color = 'var(--color-success, #1a7f4b)';
                }
                showToast(`FMU AAS sync: ${accessKey} ok`, 'success');
            } catch (error) {
                logger.error(error);
                if (fields.result) {
                    fields.result.textContent = error.message;
                    fields.result.style.color = 'var(--color-error, #c0392b)';
                }
                showToast(`FMU AAS sync failed: ${error.message}`, 'error');
            } finally {
                if (fields.syncButton) fields.syncButton.disabled = false;
            }
        }

        function initialize() {
            if (fields.keyInput) {
                fields.keyInput.addEventListener('input', () => {
                    clearAllFmuHints();
                });
                fields.keyInput.addEventListener('change', () => {
                    const accessKey = fields.keyInput.value.trim();
                    if (!accessKey) {
                        clearAllFmuHints();
                        return;
                    }
                    void fetchFmuHints(accessKey);
                });
            }
            if (fields.fileInput) {
                fields.fileInput.addEventListener('change', () => {
                    const file = fields.fileInput.files && fields.fileInput.files[0];
                    if (fields.fileName) fields.fileName.textContent = file ? file.name : 'No file chosen';
                });
            }
            if (fields.syncButton) {
                fields.syncButton.addEventListener('click', () => {
                    const accessKey = (fields.keyInput && fields.keyInput.value || '').trim();
                    const labId = (fields.labSelect && fields.labSelect.value || '').trim();
                    const file = fields.fileInput && fields.fileInput.files && fields.fileInput.files[0];
                    const extraInfo = {
                        description: (fields.description && fields.description.value || '').trim(),
                        license: (fields.license && fields.license.value || '').trim(),
                        docsUrl: (fields.docsUrl && fields.docsUrl.value || '').trim(),
                        contactEmail: (fields.contactEmail && fields.contactEmail.value || '').trim(),
                    };
                    void syncAasFmu(accessKey, labId, file || null, extraInfo);
                });
            }
        }

        return Object.freeze({
            clearAllFmuHints,
            fetchFmuHints,
            initialize,
            syncAasFmu,
        });
    }

    root.LabManagerFmuSync = Object.freeze({ createController });
})(window);
