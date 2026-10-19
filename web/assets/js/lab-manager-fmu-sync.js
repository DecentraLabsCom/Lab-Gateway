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
        let gatewayUploadedAssetUrl = '';
        let gatewayUploadedAssetAccessKey = '';

        function isGatewaySceneAssetPath(path) {
            return /^\/digital-twin-scenes\/\d+\/[a-f0-9]{64}\.glb$/i.test(String(path || ''));
        }

        function isGatewayApplicationAssetPath(path) {
            return /^\/digital-twin-apps\/\d+\/[a-f0-9]{64}\/index\.html$/i.test(String(path || ''));
        }

        function isGatewayAssetPath(path, assetType) {
            return assetType === 'glb' ? isGatewaySceneAssetPath(path) : isGatewayApplicationAssetPath(path);
        }

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
                resourceType: Number.isFinite(resourceType) ? resourceType : selectedValue ? 1 : null,
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
                digitalTwinAssetUrl: String(extraInfo.digitalTwinAssetUrl || '').trim(),
            };
        }

        function updateAssetVisibility() {
            if (!fields.assetField) return;
            const laboratory = selectedLaboratory();
            fields.assetField.hidden = laboratory.resourceType !== 1;
            if (laboratory.resourceType !== 1) {
                if (fields.assetType) fields.assetType.value = '';
                if (fields.assetUrl) fields.assetUrl.value = '';
                if (fields.assetFileInput) fields.assetFileInput.value = '';
                if (fields.assetFileName) fields.assetFileName.textContent = 'No file chosen';
                gatewayUploadedAssetUrl = '';
                gatewayUploadedAssetAccessKey = '';
                return;
            }
            if (!fields.assetUrl) return;

            const currentUrl = String(fields.assetUrl.value || '').trim();
            if (
                gatewayUploadedAssetUrl
                && currentUrl === gatewayUploadedAssetUrl
                && laboratory.accessKey !== gatewayUploadedAssetAccessKey
            ) {
                fields.assetUrl.value = '';
                gatewayUploadedAssetUrl = '';
                gatewayUploadedAssetAccessKey = '';
            }
        }

        async function importCompanionAsset(labId, accessKey, assetType) {
            if (!['glb', 'threejs-app'].includes(assetType)) {
                throw new Error('Choose GLB or Three.js application before importing a companion asset');
            }
            const response = await fetchImpl(
                `/lab-admin/digital-twin-assets/${encodeURIComponentImpl(labId)}/from-fmu`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ accessKey, assetType }),
                },
            );
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(body.detail || `Companion asset import failed (HTTP ${response.status})`);
            }
            if (!isGatewayAssetPath(body.path, assetType)) {
                throw new Error('Gateway returned an invalid digital twin asset path');
            }
            if (fields.assetUrl) fields.assetUrl.value = body.path;
            gatewayUploadedAssetUrl = body.path;
            gatewayUploadedAssetAccessKey = accessKey;
            return body;
        }

        function appendMetadataToForm(form, metadata) {
            if (metadata.description) form.append('description', metadata.description);
            if (metadata.license) form.append('license', metadata.license);
            if (metadata.documentationUrls.length) {
                form.append('documentationUrls', JSON.stringify(metadata.documentationUrls));
            }
            if (metadata.contactEmail) form.append('contactEmail', metadata.contactEmail);
        }

        async function syncAasResource(laboratory, aasxFile, assetFile, extraInfo = {}) {
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
            const assetType = isFmu
                ? String(extraInfo.digitalTwinAssetType || fields.assetType?.value || '').trim()
                : '';
            if (aasxFile && assetFile) {
                showToast('Choose either an AASX package or a visual asset for generated FMU metadata', 'error');
                return;
            }
            if (aasxFile && (assetType || extraInfo.digitalTwinAssetUrl)) {
                showToast('An uploaded AASX package must contain its own visual asset reference', 'error');
                return;
            }
            if ((assetFile || assetType || extraInfo.digitalTwinAssetUrl) && !isFmu) {
                showToast('A visual companion asset can only be attached to an FMU laboratory', 'error');
                return;
            }
            if (assetFile && !['glb', 'threejs-app'].includes(assetType)) {
                showToast('Choose whether the uploaded asset is a GLB or a Three.js application', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            try {
                const description = isFmu
                    ? await resolveDescription(accessKey, extraInfo.labDescription)
                    : String(extraInfo.labDescription || '').trim();
                const syncInfo = { ...buildMetadata(extraInfo), description };
                if (assetFile) {
                    const isGlb = assetType === 'glb';
                    const expectedExtension = isGlb ? /\.glb$/i : /\.zip$/i;
                    const maximumBytes = 50 * 1024 * 1024;
                    if (!expectedExtension.test(String(assetFile.name || '')) || assetFile.size <= 0) {
                        throw new Error(isGlb ? 'Choose a non-empty .glb scene file' : 'Choose a non-empty .zip application bundle');
                    }
                    if (assetFile.size > maximumBytes) {
                        throw new Error('Digital twin assets must be 50 MiB or smaller');
                    }
                    const uploadResponse = await fetchImpl(
                        `/lab-admin/digital-twin-assets/${encodeURIComponentImpl(labId)}`,
                        {
                            method: 'PUT',
                            headers: { 'Content-Type': isGlb ? 'model/gltf-binary' : 'application/zip' },
                            body: assetFile,
                        },
                    );
                    if (!uploadResponse.ok) {
                        const body = await uploadResponse.json().catch(() => ({}));
                        throw new Error(body.detail || `Digital twin asset upload failed (HTTP ${uploadResponse.status})`);
                    }
                    const uploadedAsset = await uploadResponse.json();
                    if (!isGatewayAssetPath(uploadedAsset.path, assetType)) {
                        throw new Error('Gateway returned an invalid digital twin asset path');
                    }
                    syncInfo.digitalTwinAssetUrl = uploadedAsset.path;
                    if (fields.assetUrl) fields.assetUrl.value = syncInfo.digitalTwinAssetUrl;
                    gatewayUploadedAssetUrl = syncInfo.digitalTwinAssetUrl;
                    gatewayUploadedAssetAccessKey = accessKey;
                }
                if (
                    isFmu
                    && !assetFile
                    && !aasxFile
                    && assetType
                    && !syncInfo.digitalTwinAssetUrl
                ) {
                    const importedAsset = await importCompanionAsset(labId, accessKey, assetType);
                    syncInfo.digitalTwinAssetUrl = importedAsset.path;
                }
                let response;
                const url = isFmu
                    ? `/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/sync`
                    : aasxFile
                        ? `/aas-admin/aas/${encodeURIComponentImpl(labId)}/sync`
                        : `/aas-admin/lab/${encodeURIComponentImpl(labId)}/sync`;
                if (aasxFile) {
                    const form = new formDataCtor();
                    form.append('file', aasxFile);
                    form.append('labId', labId);
                    appendMetadataToForm(form, syncInfo);
                    response = await fetchImpl(url, { method: 'POST', body: form });
                } else if (!isFmu) {
                    const metadata = Object.fromEntries(
                        Object.entries(syncInfo).filter(([key, value]) => (
                            key !== 'digitalTwinAssetUrl'
                            && key !== 'digitalTwinAssetType'
                            && (Array.isArray(value) ? value.length > 0 : Boolean(value))
                        )),
                    );
                    response = await fetchImpl(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ includeHeartbeat: true, metadata }),
                    });
                } else {
                    const params = new urlSearchParamsCtor();
                    params.set('labId', labId);
                    if (syncInfo.description) params.set('description', syncInfo.description);
                    if (syncInfo.license) params.set('license', syncInfo.license);
                    if (syncInfo.documentationUrls.length) {
                        params.set('documentationUrls', JSON.stringify(syncInfo.documentationUrls));
                    }
                    if (syncInfo.contactEmail) params.set('contactEmail', syncInfo.contactEmail);
                    if (syncInfo.digitalTwinAssetUrl && !aasxFile) {
                        params.set('digitalTwinAssetUrl', syncInfo.digitalTwinAssetUrl);
                    }
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
                    updateAssetVisibility();
                });
                fields.keyInput.addEventListener('change', () => {
                    const laboratory = selectedLaboratory();
                    updateAssetVisibility();
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
            if (fields.assetType) {
                if (fields.assetFileInput) {
                    fields.assetFileInput.accept = fields.assetType.value === 'glb'
                        ? '.glb,model/gltf-binary'
                        : fields.assetType.value === 'threejs-app' ? '.zip,application/zip' : '';
                }
                fields.assetType.addEventListener('change', () => {
                    if (fields.assetUrl) fields.assetUrl.value = '';
                    if (fields.assetFileInput) fields.assetFileInput.value = '';
                    if (fields.assetFileName) fields.assetFileName.textContent = 'No file chosen';
                    gatewayUploadedAssetUrl = '';
                    gatewayUploadedAssetAccessKey = '';
                    if (fields.assetFileInput) {
                        fields.assetFileInput.accept = fields.assetType.value === 'glb'
                            ? '.glb,model/gltf-binary'
                            : fields.assetType.value === 'threejs-app' ? '.zip,application/zip' : '';
                    }
                });
            }
            if (fields.assetFileInput) {
                fields.assetFileInput.addEventListener('change', () => {
                    const file = fields.assetFileInput.files && fields.assetFileInput.files[0];
                    if (fields.assetFileName) fields.assetFileName.textContent = file ? file.name : 'No file chosen';
                });
            }
            if (fields.importAssetButton) {
                fields.importAssetButton.addEventListener('click', async () => {
                    const laboratory = selectedLaboratory();
                    if (laboratory.resourceType !== 1 || !laboratory.accessKey) {
                        showToast('Select an FMU laboratory first', 'error');
                        return;
                    }
                    const assetType = fields.assetType?.value;
                    if (!assetType) {
                        showToast('Choose a visualisation type first', 'error');
                        return;
                    }
                    fields.importAssetButton.disabled = true;
                    try {
                        const asset = await importCompanionAsset(laboratory.labId, laboratory.accessKey, assetType);
                        showToast(`Companion asset imported from ${asset.source || 'FMU backend'}`, 'success');
                    } catch (error) {
                        logger.error(error);
                        showToast(`Companion asset import failed: ${error.message}`, 'error');
                    } finally {
                        fields.importAssetButton.disabled = false;
                    }
                });
            }
            if (fields.syncButton) {
                fields.syncButton.addEventListener('click', () => {
                    const laboratory = selectedLaboratory();
                    const file = fields.fileInput && fields.fileInput.files && fields.fileInput.files[0];
                    const assetFile = fields.assetFileInput && fields.assetFileInput.files && fields.assetFileInput.files[0];
                    const extraInfo = {
                        labDescription: laboratory.labDescription,
                        labDocumentation: laboratory.labDocumentation,
                        labLicense: laboratory.labLicense,
                        digitalTwinAssetUrl: (fields.assetUrl && fields.assetUrl.value || '').trim(),
                        digitalTwinAssetType: fields.assetType?.value || '',
                        contactEmail: (fields.contactEmail && fields.contactEmail.value || '').trim(),
                    };
                    void syncAasResource(laboratory, file || null, assetFile || null, extraInfo);
                });
            }
            updateAssetVisibility();
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
