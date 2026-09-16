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
            const selectedValue = (fields.keyInput && fields.keyInput.value || '').trim();
            const option = Array.from(fields.keyInput?.options || [])
                .find(candidate => String(candidate.value || '') === selectedValue);
            const resourceType = Number(option?.dataset?.resourceType);
            return {
                labId: String(option?.dataset?.labId || selectedValue).trim(),
                accessKey: String(option?.dataset?.accessKey || (resourceType === 0 ? '' : selectedValue)).trim(),
                resourceType: Number.isFinite(resourceType) ? resourceType : 1,
                labDescription: String(option?.dataset?.labDescription || '').trim(),
                labDocumentation: parseDatasetList(option?.dataset?.labDocumentation),
                labLicense: String(option?.dataset?.labLicense || '').trim(),
            };
        }

        async function fetchFmuHints(accessKey, selectedValue = (fields.keyInput?.value || '').trim()) {
            if (!accessKey) {
                clearAllFmuHints();
                return {};
            }
            try {
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/hints`);
                if (!response.ok) {
                    if ((fields.keyInput?.value || '').trim() === selectedValue) {
                        clearAllFmuHints();
                    }
                    return {};
                }
                const hints = await response.json();
                if ((fields.keyInput?.value || '').trim() !== selectedValue) {
                    return {};
                }
                fmuDescription = String(hints.description || '').trim();
                fmuDescriptionAccessKey = accessKey;
                return hints;
            } catch (_error) {
                // FMU hints are best-effort and must not block the sync form.
                if ((fields.keyInput?.value || '').trim() === selectedValue) {
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

        function buildMetadata(extraInfo = {}) {
            return {
                description: String(extraInfo.labDescription || '').trim(),
                license: String(extraInfo.labLicense || '').trim(),
                documentationUrls: parseDatasetList(extraInfo.labDocumentation),
                contactEmail: String(extraInfo.contactEmail || '').trim(),
            };
        }

        function appendMetadataToForm(form, metadata) {
            if (metadata.description) form.append('description', metadata.description);
            if (metadata.license) form.append('license', metadata.license);
            if (metadata.documentationUrls.length) {
                form.append('documentationUrls', JSON.stringify(metadata.documentationUrls));
            }
            if (metadata.contactEmail) form.append('contactEmail', metadata.contactEmail);
        }

        async function syncAasResource(laboratory, aasxFile, extraInfo = {}) {
            const { accessKey, labId, resourceType } = laboratory;
            const isFmu = resourceType === 1;
            if (!labId) {
                showToast('Select a laboratory', 'error');
                return;
            }
            if (isFmu && !accessKey) {
                showToast('Select an FMU laboratory', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            try {
                const description = isFmu
                    ? await resolveDescription(accessKey, extraInfo.labDescription)
                    : String(extraInfo.labDescription || '').trim();
                const syncInfo = { ...buildMetadata(extraInfo), description };
                let response;
                const url = isFmu
                    ? `/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/sync`
                    : aasxFile
                        ? `/aas-admin/aas/${encodeURIComponentImpl(labId)}/sync`
                        : `/aas-admin/lab/${encodeURIComponentImpl(labId)}/sync`;
                if (aasxFile) {
                    const form = new formDataCtor();
                    form.append('file', aasxFile);
                    if (labId) form.append('labId', labId);
                    appendMetadataToForm(form, syncInfo);
                    response = await fetchImpl(url, { method: 'POST', body: form });
                } else if (!isFmu) {
                    const metadata = Object.fromEntries(
                        Object.entries(syncInfo).filter(([, value]) => (
                            Array.isArray(value) ? value.length > 0 : Boolean(value)
                        )),
                    );
                    response = await fetchImpl(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ includeHeartbeat: true, metadata }),
                    });
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
                    showToast(`${isFmu ? 'FMU' : 'Physical laboratory'} AAS sync disabled: ${labId}`, 'error');
                    return;
                }
                showToast(`${isFmu ? 'FMU' : 'Physical laboratory'} AAS sync: ${labId} ok`, 'success');
            } catch (error) {
                logger.error(error);
                showToast(`AAS synchronization failed: ${error.message}`, 'error');
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
                    const laboratory = selectedLaboratory();
                    if (!laboratory.accessKey || laboratory.resourceType !== 1) {
                        clearAllFmuHints();
                        return;
                    }
                    void fetchFmuHints(laboratory.accessKey, (fields.keyInput?.value || '').trim());
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
                    const file = fields.fileInput && fields.fileInput.files && fields.fileInput.files[0];
                    const extraInfo = {
                        labDescription: laboratory.labDescription,
                        labDocumentation: laboratory.labDocumentation,
                        labLicense: laboratory.labLicense,
                        contactEmail: (fields.contactEmail && fields.contactEmail.value || '').trim(),
                    };
                    void syncAasResource(laboratory, file || null, extraInfo);
                });
            }
        }

        return Object.freeze({
            clearAllFmuHints,
            fetchFmuHints,
            initialize,
            syncAasResource,
        });
    }

    root.LabManagerFmuSync = Object.freeze({ createController });
})(window);
