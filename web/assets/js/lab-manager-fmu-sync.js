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
        let fmuDescription = '';
        let fmuDescriptionAccessKey = '';

        function parseDatasetList(value) {
            if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean);
            try {
                const parsed = JSON.parse(value || '[]');
                return Array.isArray(parsed) ? parsed.map(item => String(item).trim()).filter(Boolean) : [];
            } catch (_error) {
                return [];
            }
        }

        function clearAllFmuHints() {
            fmuDescription = '';
            fmuDescriptionAccessKey = '';
        }

        function selectedLaboratory() {
            const accessKey = (fields.keyInput && fields.keyInput.value || '').trim();
            const option = Array.from(fields.keyInput?.options || [])
                .find(candidate => String(candidate.value || '') === accessKey);
            return {
                accessKey,
                labId: String(option?.dataset?.labId || '').trim(),
                labDescription: String(option?.dataset?.labDescription || '').trim(),
                labDocumentation: parseDatasetList(option?.dataset?.labDocumentation),
                labLicense: String(option?.dataset?.labLicense || '').trim(),
            };
        }

        async function fetchFmuHints(accessKey) {
            if (!accessKey) {
                clearAllFmuHints();
                return {};
            }
            try {
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/hints`);
                if (!response.ok) {
                    if ((fields.keyInput?.value || '').trim() === accessKey) {
                        clearAllFmuHints();
                    }
                    return {};
                }
                const hints = await response.json();
                if ((fields.keyInput?.value || '').trim() !== accessKey) {
                    return {};
                }
                fmuDescription = String(hints.description || '').trim();
                fmuDescriptionAccessKey = accessKey;
                return hints;
            } catch (_error) {
                // FMU hints are best-effort and must not block the sync form.
                if ((fields.keyInput?.value || '').trim() === accessKey) {
                    fmuDescription = '';
                    fmuDescriptionAccessKey = '';
                }
                return {};
            }
        }

        async function resolveDescription(accessKey, laboratoryDescription) {
            if (fmuDescriptionAccessKey !== accessKey) {
                await fetchFmuHints(accessKey);
            }
            return fmuDescription || String(laboratoryDescription || '').trim();
        }

        async function syncAasFmu(accessKey, labId, aasxFile, extraInfo = {}) {
            if (!accessKey) {
                showToast('Select an FMU laboratory', 'error');
                return;
            }
            if (!labId) {
                showToast('Select an FMU laboratory', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            if (fields.result) fields.result.textContent = '';
            try {
                const description = await resolveDescription(accessKey, extraInfo.labDescription);
                const syncInfo = {
                    description,
                    license: String(extraInfo.labLicense || '').trim(),
                    documentationUrls: parseDatasetList(extraInfo.labDocumentation),
                    contactEmail: String(extraInfo.contactEmail || '').trim(),
                };
                let response;
                const url = `/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/sync`;
                if (aasxFile) {
                    const form = new formDataCtor();
                    form.append('file', aasxFile);
                    if (labId) form.append('labId', labId);
                    if (syncInfo.description) form.append('description', syncInfo.description);
                    if (syncInfo.license) form.append('license', syncInfo.license);
                    if (syncInfo.documentationUrls.length) {
                        form.append('documentationUrls', JSON.stringify(syncInfo.documentationUrls));
                    }
                    if (syncInfo.contactEmail) form.append('contactEmail', syncInfo.contactEmail);
                    response = await fetchImpl(url, { method: 'POST', body: form });
                } else {
                    const params = new urlSearchParamsCtor();
                    if (labId) params.set('labId', labId);
                    if (syncInfo.description) params.set('description', syncInfo.description);
                    if (syncInfo.license) params.set('license', syncInfo.license);
                    if (syncInfo.documentationUrls.length) {
                        params.set('documentationUrls', JSON.stringify(syncInfo.documentationUrls));
                    }
                    if (syncInfo.contactEmail) params.set('contactEmail', syncInfo.contactEmail);
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
                if (data.disabled === true) {
                    const message = 'AAS synchronization is disabled on this gateway.';
                    if (fields.result) {
                        fields.result.textContent = message;
                        fields.result.style.color = 'var(--color-error, #c0392b)';
                    }
                    showToast(`FMU AAS sync disabled: ${accessKey}`, 'error');
                    return;
                }
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
                    const laboratory = selectedLaboratory();
                    const accessKey = laboratory.accessKey;
                    const labId = laboratory.labId;
                    const file = fields.fileInput && fields.fileInput.files && fields.fileInput.files[0];
                    const extraInfo = {
                        labDescription: laboratory.labDescription,
                        labDocumentation: laboratory.labDocumentation,
                        labLicense: laboratory.labLicense,
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
