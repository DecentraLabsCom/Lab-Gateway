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
        let gatewayUploadedSceneUrl = '';
        let gatewayUploadedSceneAccessKey = '';
        const smartFactoryDemoAccessKey = 'SmartFactoryCell.fmu';

        function isGatewaySceneAssetPath(path) {
            return /^\/digital-twin-scenes\/\d+\/[a-f0-9]{64}\.glb$/i.test(String(path || ''));
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
                digitalTwinSceneUrl: String(extraInfo.digitalTwinSceneUrl || '').trim(),
            };
        }

        function updateSceneUrlVisibility() {
            if (!fields.sceneUrlField) return;
            const laboratory = selectedLaboratory();
            fields.sceneUrlField.hidden = laboratory.resourceType !== 1;
            if (!fields.sceneUrl || laboratory.resourceType !== 1) return;

            const currentUrl = String(fields.sceneUrl.value || '').trim();
            if (
                gatewayUploadedSceneUrl
                && currentUrl === gatewayUploadedSceneUrl
                && laboratory.accessKey !== gatewayUploadedSceneAccessKey
            ) {
                fields.sceneUrl.value = '';
            }
        }

        async function importCompanionScene(labId, accessKey) {
            const response = await fetchImpl(
                `/lab-admin/digital-twin-scenes/${encodeURIComponentImpl(labId)}/from-fmu`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ accessKey }),
                },
            );
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(body.detail || `Companion GLB import failed (HTTP ${response.status})`);
            }
            if (!isGatewaySceneAssetPath(body.path)) {
                throw new Error('Gateway returned an invalid GLB asset path');
            }
            if (fields.sceneUrl) fields.sceneUrl.value = body.path;
            gatewayUploadedSceneUrl = body.path;
            gatewayUploadedSceneAccessKey = accessKey;
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

        async function syncAasResource(laboratory, aasxFile, sceneFile, extraInfo = {}) {
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
            if (aasxFile && sceneFile) {
                showToast('Choose either an AASX package or a GLB for generated FMU metadata', 'error');
                return;
            }
            if (sceneFile && !isFmu) {
                showToast('A GLB companion can only be attached to an FMU laboratory', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            try {
                const description = isFmu
                    ? await resolveDescription(accessKey, extraInfo.labDescription)
                    : String(extraInfo.labDescription || '').trim();
                const syncInfo = { ...buildMetadata(extraInfo), description };
                if (sceneFile) {
                    if (!/\.glb$/i.test(String(sceneFile.name || '')) || sceneFile.size <= 0) {
                        throw new Error('Choose a non-empty .glb scene file');
                    }
                    if (sceneFile.size > 50 * 1024 * 1024) {
                        throw new Error('GLB scenes must be 50 MiB or smaller');
                    }
                    const uploadResponse = await fetchImpl(
                        `/lab-admin/digital-twin-scenes/${encodeURIComponentImpl(labId)}`,
                        {
                            method: 'PUT',
                            headers: { 'Content-Type': 'model/gltf-binary' },
                            body: sceneFile,
                        },
                    );
                    if (!uploadResponse.ok) {
                        const body = await uploadResponse.json().catch(() => ({}));
                        throw new Error(body.detail || `GLB upload failed (HTTP ${uploadResponse.status})`);
                    }
                    const uploadedScene = await uploadResponse.json();
                    if (!isGatewaySceneAssetPath(uploadedScene.path)) {
                        throw new Error('Gateway returned an invalid GLB asset path');
                    }
                    syncInfo.digitalTwinSceneUrl = uploadedScene.path;
                    if (fields.sceneUrl) fields.sceneUrl.value = syncInfo.digitalTwinSceneUrl;
                    gatewayUploadedSceneUrl = syncInfo.digitalTwinSceneUrl;
                    gatewayUploadedSceneAccessKey = accessKey;
                }
                if (
                    isFmu
                    && !sceneFile
                    && !aasxFile
                    && accessKey === smartFactoryDemoAccessKey
                    && !syncInfo.digitalTwinSceneUrl
                ) {
                    const importedScene = await importCompanionScene(labId, accessKey);
                    syncInfo.digitalTwinSceneUrl = importedScene.path;
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
                            key !== 'digitalTwinSceneUrl'
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
                    if (syncInfo.digitalTwinSceneUrl && !aasxFile) {
                        params.set('digitalTwinSceneUrl', syncInfo.digitalTwinSceneUrl);
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
                    updateSceneUrlVisibility();
                });
                fields.keyInput.addEventListener('change', () => {
                    const laboratory = selectedLaboratory();
                    updateSceneUrlVisibility();
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
            if (fields.sceneFileInput) {
                fields.sceneFileInput.addEventListener('change', () => {
                    const file = fields.sceneFileInput.files && fields.sceneFileInput.files[0];
                    if (fields.sceneFileName) fields.sceneFileName.textContent = file ? file.name : 'No file chosen';
                });
            }
            if (fields.importSceneButton) {
                fields.importSceneButton.addEventListener('click', async () => {
                    const laboratory = selectedLaboratory();
                    if (laboratory.resourceType !== 1 || !laboratory.accessKey) {
                        showToast('Select an FMU laboratory first', 'error');
                        return;
                    }
                    fields.importSceneButton.disabled = true;
                    try {
                        const scene = await importCompanionScene(laboratory.labId, laboratory.accessKey);
                        showToast(`Companion GLB imported from ${scene.source || 'FMU backend'}`, 'success');
                    } catch (error) {
                        logger.error(error);
                        showToast(`Companion GLB import failed: ${error.message}`, 'error');
                    } finally {
                        fields.importSceneButton.disabled = false;
                    }
                });
            }
            if (fields.syncButton) {
                fields.syncButton.addEventListener('click', () => {
                    const laboratory = selectedLaboratory();
                    const file = fields.fileInput && fields.fileInput.files && fields.fileInput.files[0];
                    const sceneFile = fields.sceneFileInput && fields.sceneFileInput.files && fields.sceneFileInput.files[0];
                    const extraInfo = {
                        labDescription: laboratory.labDescription,
                        labDocumentation: laboratory.labDocumentation,
                        labLicense: laboratory.labLicense,
                        digitalTwinSceneUrl: (fields.sceneUrl && fields.sceneUrl.value || '').trim(),
                        contactEmail: (fields.contactEmail && fields.contactEmail.value || '').trim(),
                    };
                    void syncAasResource(laboratory, file || null, sceneFile || null, extraInfo);
                });
            }
            updateSceneUrlVisibility();
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
