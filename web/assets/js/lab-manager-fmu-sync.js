(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        formDataCtor = root.FormData,
        urlSearchParamsCtor = root.URLSearchParams,
        documentImpl = typeof document === 'undefined' ? root.document : document,
        encodeURIComponentImpl = encodeURIComponent,
        logger = console,
    }) {
        let fmuDescription = '';
        let fmuDescriptionAccessKey = '';
        let gatewayUploadedAssetUrl = '';
        let gatewayUploadedAssetAccessKey = '';
        let gatewayUploadedAssetType = '';
        let acknowledgedAssetValidationKey = '';
        let lastAssetValidation = null;

        function renderAccessPolicyStatus(status) {
            const panel = fields.accessPolicyStatus;
            const regenerateButton = fields.regenerateAccessPolicyButton;
            if (!panel) return;
            const state = String(status?.state || 'unavailable');
            const labels = {
                generated: 'Generated defaults are active.',
                customized: 'Provider-defined access rules are active.',
                stale: 'Rules no longer match the current FMU interface.',
                invalid: 'Rules are invalid and are not being applied.',
                'sync-error': 'AAS synchronization failed. Access rules could not be rechecked; use “Check access rules” before relying on Marketplace controls.',
                'fmi-default': 'No AAS rules are linked; FMI-derived defaults are active.',
                unavailable: 'Access rule status is unavailable; simulations fail closed.',
            };
            panel.dataset.state = state;
            panel.dataset.status = ['stale', 'invalid', 'sync-error', 'unavailable'].includes(state)
                || (state === 'fmi-default' && status?.aasLinked === true)
                ? 'warning'
                : 'passed';
            panel.textContent = labels[state] || labels.unavailable;
            if (status && Number.isFinite(Number(status.readableVariableCount))) {
                panel.textContent += ` Readable variables: ${Number(status.readableVariableCount)}; writable variables: ${Number(status.writableVariableCount || 0)}.`;
            }
            if (regenerateButton) {
                regenerateButton.hidden = status?.regenerationAvailable !== true;
                regenerateButton.disabled = false;
            }
        }

        async function loadAccessPolicyStatus(laboratory = selectedLaboratory()) {
            if (!fields.accessPolicyStatus) return null;
            if (laboratory.resourceType !== 1 || !laboratory.accessKey || !laboratory.labId) {
                fields.accessPolicyStatus.textContent = 'Select an FMU to check its variable access rules.';
                delete fields.accessPolicyStatus.dataset.state;
                if (fields.regenerateAccessPolicyButton) fields.regenerateAccessPolicyButton.hidden = true;
                return null;
            }
            fields.accessPolicyStatus.textContent = 'Checking FMU access rules…';
            const query = new urlSearchParamsCtor({ labId: laboratory.labId });
            try {
                const response = await fetchImpl(
                    `/aas-admin/fmu/${encodeURIComponentImpl(laboratory.accessKey)}/access-policy?${query.toString()}`,
                );
                const status = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(status.detail || `HTTP ${response.status}`);
                renderAccessPolicyStatus(status);
                return status;
            } catch (_error) {
                renderAccessPolicyStatus({ state: 'unavailable', regenerationAvailable: false });
                return null;
            }
        }

        async function regenerateAccessPolicy() {
            const laboratory = selectedLaboratory();
            if (laboratory.resourceType !== 1 || !laboratory.accessKey || !laboratory.labId) {
                showToast('Select an FMU laboratory first', 'error');
                return;
            }
            const confirmAction = root.confirm;
            if (typeof confirmAction !== 'function' || !confirmAction.call(root,
                'Replace the current variable access rules with FMI-derived defaults? Provider changes will be lost.')) {
                return;
            }
            const button = fields.regenerateAccessPolicyButton;
            if (button) button.disabled = true;
            try {
                const query = new urlSearchParamsCtor({
                    labId: laboratory.labId,
                    regenerateAccessPolicy: 'true',
                });
                const response = await fetchImpl(
                    `/aas-admin/fmu/${encodeURIComponentImpl(laboratory.accessKey)}/sync?${query.toString()}`,
                    { method: 'POST' },
                );
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
                if (body.disabled === true) throw new Error('AAS access rules are unavailable on this Gateway');
                showToast('Default FMU access rules regenerated', 'success');
                await loadAccessPolicyStatus(laboratory);
            } catch (error) {
                showToast(`Access rule regeneration failed: ${error.message}`, 'error');
                if (button) button.disabled = false;
            }
        }

        function isGatewaySceneAssetPath(path) {
            return /^\/digital-twin-scenes\/\d+\/[a-f0-9]{64}\.glb$/i.test(String(path || ''));
        }

        function isGatewayApplicationAssetPath(path) {
            return /^\/digital-twin-apps\/\d+\/[a-f0-9]{64}\/index\.html$/i.test(String(path || ''));
        }

        function isGatewayAssetPath(path, assetType) {
            return assetType === 'glb' ? isGatewaySceneAssetPath(path) : isGatewayApplicationAssetPath(path);
        }

        function inferAssetTypeFromFile(file) {
            const name = String(file?.name || '').toLowerCase();
            if (name.endsWith('.glb')) return 'glb';
            if (name.endsWith('.zip')) return 'threejs-app';
            return '';
        }

        function inferAssetTypeFromUrl(value) {
            const url = String(value || '').trim();
            if (isGatewaySceneAssetPath(url) || /\.glb(?:[?#].*)?$/i.test(url)) return 'glb';
            if (isGatewayApplicationAssetPath(url) || /\.(?:webapp\.)?zip(?:[?#].*)?$/i.test(url)) return 'threejs-app';
            return '';
        }

        function updateAssetFileAccept(assetType) {
            if (!fields.assetFileInput) return;
            fields.assetFileInput.accept = assetType === 'glb'
                ? '.glb,model/gltf-binary'
                : assetType === 'threejs-app'
                    ? '.zip,application/zip'
                    : assetType === 'auto'
                        ? '.glb,.zip,model/gltf-binary,application/zip'
                        : '';
        }

        function assetValidationKey(labId, accessKey, assetType, assetFile, assetUrl) {
            const assetIdentity = assetFile
                ? `file:${assetFile.name}:${assetFile.size}:${assetFile.lastModified}`
                : `url:${String(assetUrl || '').trim()}`;
            return [labId, accessKey, assetType, assetIdentity].join('|');
        }

        function clearAssetValidation() {
            acknowledgedAssetValidationKey = '';
            lastAssetValidation = null;
            const panel = fields.assetValidation;
            if (!panel) return;
            panel.hidden = true;
            panel.replaceChildren?.();
            panel.textContent = '';
            delete panel.dataset.status;
        }

        function renderAssetValidation(report) {
            const panel = fields.assetValidation;
            if (!panel) return;
            panel.replaceChildren?.();
            panel.textContent = '';
            if (!report || typeof report !== 'object') {
                panel.hidden = true;
                delete panel.dataset.status;
                return;
            }

            panel.hidden = false;
            panel.dataset.status = String(report.status || 'not_checked');
            const summary = documentImpl.createElement('p');
            summary.textContent = String(report.message || 'Asset validation is incomplete.');
            panel.appendChild(summary);

            if (Number.isFinite(Number(report.bindingCount))) {
                const counts = documentImpl.createElement('p');
                counts.textContent = `FMI bindings checked: ${Number(report.validBindingCount || 0)} of ${Number(report.bindingCount)}.`;
                panel.appendChild(counts);
            }

            const issues = Array.isArray(report.issues) ? report.issues.slice(0, 20) : [];
            if (issues.length) {
                const list = documentImpl.createElement('ul');
                issues.forEach(issue => {
                    const item = documentImpl.createElement('li');
                    const node = String(issue?.node || 'Scene');
                    const variable = typeof issue?.variable === 'string' ? ` · ${issue.variable}` : '';
                    item.textContent = `${node}${variable}: ${String(issue?.message || 'Binding issue')}`;
                    list.appendChild(item);
                });
                panel.appendChild(list);
            }
            if (Number(report.issueCount) > issues.length) {
                const remainder = documentImpl.createElement('p');
                remainder.textContent = `${Number(report.issueCount) - issues.length} additional findings are not shown.`;
                panel.appendChild(remainder);
            }
        }

        function needsAssetValidationAcknowledgement(report) {
            return ['warning', 'not_checked', 'unavailable'].includes(String(report?.status || ''));
        }

        function reviewAssetValidation(report, key) {
            if (!report || typeof report !== 'object') {
                report = {
                    status: 'not_checked',
                    message: 'The Gateway did not return an asset validation report.',
                    issueCount: 0,
                    issues: [],
                };
            }
            lastAssetValidation = { key, report };
            renderAssetValidation(report);
            if (!needsAssetValidationAcknowledgement(report) || acknowledgedAssetValidationKey === key) return true;
            acknowledgedAssetValidationKey = key;
            showToast('Review the digital twin validation findings, then select Sync AAS again to publish.', 'info');
            return false;
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
            const wasHidden = fields.assetField.hidden;
            fields.assetField.hidden = laboratory.resourceType !== 1;
            if (laboratory.resourceType !== 1) {
                if (fields.assetType) fields.assetType.value = '';
                if (fields.assetUrl) fields.assetUrl.value = '';
                if (fields.assetFileInput) fields.assetFileInput.value = '';
                if (fields.assetFileName) fields.assetFileName.textContent = 'No file chosen';
                gatewayUploadedAssetUrl = '';
                gatewayUploadedAssetAccessKey = '';
                gatewayUploadedAssetType = '';
                return;
            }
            if (wasHidden && fields.assetType && !fields.assetType.value) {
                fields.assetType.value = 'auto';
                updateAssetFileAccept('auto');
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
                gatewayUploadedAssetType = '';
            }
        }

        async function importCompanionAsset(labId, accessKey, assetType) {
            if (!['auto', 'glb', 'threejs-app'].includes(assetType)) {
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
                const error = new Error(body.detail || `Companion asset import failed (HTTP ${response.status})`);
                error.status = response.status;
                throw error;
            }
            const resolvedAssetType = assetType === 'auto' ? String(body.assetType || '').trim() : assetType;
            if (!['glb', 'threejs-app'].includes(resolvedAssetType) || !isGatewayAssetPath(body.path, resolvedAssetType)) {
                throw new Error('Gateway returned an invalid digital twin asset path');
            }
            if (fields.assetUrl) fields.assetUrl.value = body.path;
            gatewayUploadedAssetUrl = body.path;
            gatewayUploadedAssetAccessKey = accessKey;
            gatewayUploadedAssetType = resolvedAssetType;
            lastAssetValidation = {
                key: assetValidationKey(labId, accessKey, resolvedAssetType, null, body.path),
                report: body.validation,
            };
            renderAssetValidation(body.validation);
            return { ...body, assetType: resolvedAssetType };
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
            const selectedAssetType = isFmu
                ? String(extraInfo.digitalTwinAssetType || fields.assetType?.value || '').trim()
                : '';
            let assetType = selectedAssetType;
            if (assetType === 'auto') {
                assetType = assetFile
                    ? inferAssetTypeFromFile(assetFile)
                    : gatewayUploadedAssetUrl === String(extraInfo.digitalTwinAssetUrl || '').trim()
                        ? gatewayUploadedAssetType
                        : inferAssetTypeFromUrl(extraInfo.digitalTwinAssetUrl);
            }
            const hasVisualAsset = Boolean(
                assetFile
                || extraInfo.digitalTwinAssetUrl
                || (selectedAssetType && selectedAssetType !== 'auto'),
            );
            if (aasxFile && assetFile) {
                showToast('Choose either an AASX package or a visual asset for generated FMU metadata', 'error');
                return;
            }
            if (aasxFile && hasVisualAsset) {
                showToast('An uploaded AASX package must contain its own visual asset reference', 'error');
                return;
            }
            if (hasVisualAsset && !isFmu) {
                showToast('A visual companion asset can only be attached to an FMU laboratory', 'error');
                return;
            }
            if (assetFile && !['glb', 'threejs-app'].includes(assetType)) {
                showToast('Choose whether the uploaded asset is a GLB or a Three.js application', 'error');
                return;
            }
            if (fields.syncButton) fields.syncButton.disabled = true;
            let syncAttempted = false;
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
                            headers: {
                                'Content-Type': isGlb ? 'model/gltf-binary' : 'application/zip',
                                'X-FMU-Access-Key': accessKey,
                            },
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
                    const validationKey = assetValidationKey(labId, accessKey, assetType, assetFile, '');
                    if (!reviewAssetValidation(uploadedAsset.validation, validationKey)) return;
                    syncInfo.digitalTwinAssetUrl = uploadedAsset.path;
                    if (fields.assetUrl) fields.assetUrl.value = syncInfo.digitalTwinAssetUrl;
                    gatewayUploadedAssetUrl = syncInfo.digitalTwinAssetUrl;
                    gatewayUploadedAssetAccessKey = accessKey;
                    gatewayUploadedAssetType = assetType;
                }
                if (
                    isFmu
                    && !assetFile
                    && !aasxFile
                    && selectedAssetType
                    && !syncInfo.digitalTwinAssetUrl
                ) {
                    try {
                        const importedAsset = await importCompanionAsset(labId, accessKey, selectedAssetType);
                        syncInfo.digitalTwinAssetUrl = importedAsset.path;
                        const validationKey = assetValidationKey(labId, accessKey, importedAsset.assetType, null, importedAsset.path);
                        if (!reviewAssetValidation(importedAsset.validation, validationKey)) return;
                    } catch (error) {
                        if (selectedAssetType !== 'auto' || error.status !== 404) throw error;
                        showToast('No REF visual asset or same-name companion was found. Sync can continue; upload a .webapp.zip or .glb if needed.', 'info');
                    }
                } else if (!assetFile && assetType && !aasxFile && syncInfo.digitalTwinAssetUrl) {
                    const validationKey = assetValidationKey(labId, accessKey, assetType, null, syncInfo.digitalTwinAssetUrl);
                    const knownValidation = lastAssetValidation?.key === validationKey
                        ? lastAssetValidation.report
                        : null;
                    const report = knownValidation || {
                        assetType,
                        status: 'not_checked',
                        message: assetType === 'glb'
                            ? 'This external GLB was not inspected by the Gateway. Marketplace will try to load it when the viewer opens.'
                            : 'The application package was not inspected by the Gateway.',
                        bindingCount: 0,
                        validBindingCount: 0,
                        issueCount: 0,
                        issues: [],
                    };
                    if (!reviewAssetValidation(report, validationKey)) return;
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
                    syncAttempted = true;
                    response = await fetchImpl(url, { method: 'POST', body: form });
                } else if (!isFmu) {
                    const metadata = Object.fromEntries(
                        Object.entries(syncInfo).filter(([key, value]) => (
                            key !== 'digitalTwinAssetUrl'
                            && key !== 'digitalTwinAssetType'
                            && (Array.isArray(value) ? value.length > 0 : Boolean(value))
                        )),
                    );
                    syncAttempted = true;
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
                    syncAttempted = true;
                    response = await fetchImpl(url + query, { method: 'POST' });
                }
                if (response.status === 403) {
                    if (isFmu) renderAccessPolicyStatus({ state: 'sync-error' });
                    showToast('AAS admin unavailable in Lite mode or blocked by gateway policy', 'error');
                    return;
                }
                if (response.status === 401) {
                    if (isFmu) renderAccessPolicyStatus({ state: 'sync-error' });
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                if (!response.ok) {
                    const body = await response.json().catch(() => ({}));
                    throw new Error(body.detail || `HTTP ${response.status}`);
                }
                const data = await response.json();
                if (data.disabled === true) {
                    if (isFmu) renderAccessPolicyStatus({ state: 'sync-error' });
                    showToast(`${isFmu ? 'FMU' : 'Physical laboratory'} AAS sync disabled: ${labId}`, 'error');
                    return;
                }
                showToast(`${isFmu ? 'FMU' : 'Physical laboratory'} AAS sync: ${labId} ok`, 'success');
                if (isFmu) await loadAccessPolicyStatus(laboratory);
            } catch (error) {
                logger.error(error);
                if (isFmu && syncAttempted) renderAccessPolicyStatus({ state: 'sync-error' });
                showToast(`AAS synchronization failed: ${error.message}`, 'error');
            } finally {
                if (fields.syncButton) fields.syncButton.disabled = false;
            }
        }

        function initialize() {
            if (fields.keyInput) {
                fields.keyInput.addEventListener('input', () => {
                    clearAllFmuHints();
                    clearAssetValidation();
                    updateAssetVisibility();
                });
                fields.keyInput.addEventListener('change', () => {
                    const laboratory = selectedLaboratory();
                    updateAssetVisibility();
                    void loadAccessPolicyStatus(laboratory);
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
                updateAssetFileAccept(fields.assetType.value);
                fields.assetType.addEventListener('change', () => {
                    clearAssetValidation();
                    if (fields.assetUrl) fields.assetUrl.value = '';
                    if (fields.assetFileInput) fields.assetFileInput.value = '';
                    if (fields.assetFileName) fields.assetFileName.textContent = 'No file chosen';
                    gatewayUploadedAssetUrl = '';
                    gatewayUploadedAssetAccessKey = '';
                    gatewayUploadedAssetType = '';
                    updateAssetFileAccept(fields.assetType.value);
                });
            }
            if (fields.assetFileInput) {
                fields.assetFileInput.addEventListener('change', () => {
                    clearAssetValidation();
                    const file = fields.assetFileInput.files && fields.assetFileInput.files[0];
                    if (fields.assetFileName) fields.assetFileName.textContent = file ? file.name : 'No file chosen';
                });
            }
            if (fields.assetUrl) {
                fields.assetUrl.addEventListener('input', clearAssetValidation);
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
                        const validationKey = assetValidationKey(laboratory.labId, laboratory.accessKey, asset.assetType, null, asset.path);
                        if (needsAssetValidationAcknowledgement(asset.validation)) {
                            acknowledgedAssetValidationKey = validationKey;
                            showToast('Review the validation findings before synchronizing the AAS.', 'info');
                        } else {
                            showToast(`Companion asset imported (${asset.assetSource || asset.source || 'FMU backend'})`, 'success');
                        }
                    } catch (error) {
                        logger.error(error);
                        if (assetType === 'auto' && error.status === 404) {
                            showToast('No REF visual asset or same-name companion was found. Upload a .webapp.zip or .glb if you want to add one.', 'info');
                        } else {
                            showToast(`Companion asset import failed: ${error.message}`, 'error');
                        }
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
            fields.checkAccessPolicyButton?.addEventListener('click', () => {
                void loadAccessPolicyStatus();
            });
            fields.regenerateAccessPolicyButton?.addEventListener('click', () => {
                void regenerateAccessPolicy();
            });
            updateAssetVisibility();
        }

        return Object.freeze({
            clearAllFmuHints,
            fetchFmuHints,
            initialize,
            loadAccessPolicyStatus,
            regenerateAccessPolicy,
            renderAccessPolicyStatus,
            syncAasResource,
        });
    }

    root.LabManagerFmuSync = Object.freeze({ createController });
})(window);
