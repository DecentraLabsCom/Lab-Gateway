(function (root) {
    'use strict';

    function defaultEscapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function createController({
        fields = {},
        fetchImpl,
        showToast,
        escapeHtml = defaultEscapeHtml,
        confirmImpl = () => true,
        resolveLabDisplayName = lab => `Lab #${lab?.labId || ''}`,
        encodeURIComponentImpl = encodeURIComponent,
        logger = console,
    }) {
        const escape = typeof escapeHtml === 'function' ? escapeHtml : defaultEscapeHtml;
        let managedLabs = [];
        let associations = [];
        let bound = false;

        function associationUrl(labId, action) {
            return `/aas-admin/aas/${encodeURIComponentImpl(labId)}/${action}`;
        }

        function resolveLabName(labId) {
            const lab = managedLabs.find(candidate => String(candidate?.labId || '').trim() === labId);
            return lab ? String(resolveLabDisplayName(lab) || `Lab #${labId}`) : `Lab #${labId}`;
        }

        function formatBytes(value) {
            if (value == null || value === '') return 'Not applicable';
            const size = Number(value);
            if (!Number.isFinite(size) || size < 0) return 'Unknown size';
            if (size < 1024) return `${size} B`;
            if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
            return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
        }

        function setStatus(message, isError = false) {
            if (!fields.packageStatus) return;
            fields.packageStatus.textContent = message;
            fields.packageStatus.classList?.toggle('error', isError);
        }

        function renderPackageList() {
            const target = fields.packageList;
            if (!target) return;
            if (!associations.length) {
                target.innerHTML = '<div class="empty">No AAS associations registered.</div>';
                return;
            }

            target.innerHTML = `
                <table class="mini-table aasx-package-table">
                    <thead>
                        <tr>
                            <th>Laboratory</th>
                            <th>AAS association</th>
                            <th>Resources</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${associations.map(association => {
                            const labId = String(association?.labId || '').trim();
                            const source = String(association?.source || 'generated').trim().toLowerCase();
                            const sourceLabel = source === 'linked'
                                ? 'Linked'
                                : source === 'imported' ? 'Imported' : 'Generated';
                            const filename = String(association?.filename || `${labId}.aasx`);
                            const targetAasId = String(association?.targetAasId || association?.shellIds?.[0] || '').trim();
                            const associationLabel = source === 'linked'
                                ? targetAasId
                                : source === 'imported'
                                    ? filename
                                    : 'Generated from laboratory metadata';
                            const sizeLabel = association?.size == null
                                ? (source === 'generated' ? 'Current BaSyx resources' : 'External AAS shell')
                                : formatBytes(association.size);
                            const downloadUrl = association?.downloadUrl || associationUrl(labId, 'download');
                            const shellCount = Array.isArray(association?.shellIds) ? association.shellIds.length : 0;
                            const submodelCount = Array.isArray(association?.submodelIds) ? association.submodelIds.length : 0;
                            const deleteLabel = source === 'linked' ? 'Unlink' : 'Delete';
                            return `
                                <tr>
                                    <td>
                                        <strong>${escape(resolveLabName(labId))}</strong>
                                        <div class="muted-text">Lab #${escape(labId)}</div>
                                    </td>
                                    <td>
                                        <strong>${escape(sourceLabel)}</strong>
                                        <div><code>${escape(associationLabel)}</code></div>
                                        <div class="muted-text">${escape(sizeLabel)}</div>
                                    </td>
                                    <td>
                                        <div>${shellCount} shell${shellCount === 1 ? '' : 's'}</div>
                                        <div class="muted-text">${submodelCount} submodel${submodelCount === 1 ? '' : 's'}</div>
                                    </td>
                                    <td class="lab-actions">
                                        <button class="mini-btn" type="button" data-aasx-view="${escape(labId)}">
                                            <i class="fas fa-eye" aria-hidden="true"></i> View
                                        </button>
                                        <a class="mini-btn" href="${escape(downloadUrl)}" download>
                                            <i class="fas fa-download" aria-hidden="true"></i> Download
                                        </a>
                                        <button class="mini-btn danger" type="button" data-aasx-delete="${escape(labId)}">
                                            <i class="fas ${source === 'linked' ? 'fa-unlink' : 'fa-trash'}" aria-hidden="true"></i> ${deleteLabel}
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
        }

        function clearPackages(message = 'No AAS associations registered.') {
            associations = [];
            renderPackageList();
            setStatus(message);
        }

        async function responseError(response) {
            const body = await response.json().catch(() => ({}));
            return body.detail || body.error || `HTTP ${response.status}`;
        }

        async function loadPackages(options = {}) {
            try {
                const response = await fetchImpl('/aas-admin/aas/catalog', options);
                if (response.status === 401) {
                    clearPackages('Lab Manager session required to load AAS associations.');
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load AAS associations', 'error');
                    return false;
                }
                if (response.status === 403) {
                    clearPackages('AAS administration is unavailable in Lite mode.');
                    return false;
                }
                if (!response.ok) throw new Error(await responseError(response));
                const body = await response.json().catch(() => ({}));
                associations = Array.isArray(body.associations) ? body.associations : [];
                renderPackageList();
                setStatus(associations.length ? `${associations.length} AAS association${associations.length === 1 ? '' : 's'} registered.` : 'No AAS associations registered.');
                if (body.warning) showToast(`AAS association list is incomplete: ${body.warning}`, 'warning');
                return true;
            } catch (error) {
                logger.warn('Unable to load AAS associations', error);
                clearPackages('Unable to load AAS associations.');
                if (options.notifyError) showToast(`AAS association load failed: ${error.message}`, 'error');
                return false;
            }
        }

        function renderView(association) {
            if (!fields.viewModal) return;
            const labId = String(association?.labId || '').trim();
            const source = String(association?.source || 'generated').trim().toLowerCase();
            const sourceLabel = source === 'linked'
                ? 'Linked'
                : source === 'imported' ? 'Imported' : 'Generated';
            const filename = String(association?.filename || `${labId}.aasx`);
            const targetAasId = String(association?.targetAasId || '').trim();
            const shellIds = Array.isArray(association?.shellIds) ? association.shellIds : [];
            const submodelIds = Array.isArray(association?.submodelIds) ? association.submodelIds : [];
            if (fields.viewTitle) fields.viewTitle.textContent = `${sourceLabel} AAS association`;
            if (fields.viewBody) {
                const renderIds = (ids, emptyLabel) => ids.length
                    ? `<ul>${ids.map(id => `<li><code>${escape(id)}</code></li>`).join('')}</ul>`
                    : `<p class="muted-text">${escape(emptyLabel)}</p>`;
                fields.viewBody.innerHTML = `
                    <div class="aasx-view-summary">
                        <div><span class="muted-text">Laboratory</span><strong>${escape(resolveLabName(labId))}</strong></div>
                        <div><span class="muted-text">Source</span><strong>${escape(sourceLabel)}</strong></div>
                        <div><span class="muted-text">AASX source</span><strong>${escape(source === 'imported' ? filename : source === 'linked' ? targetAasId : 'Generated from BaSyx')}</strong></div>
                        <div><span class="muted-text">Size</span><strong>${escape(formatBytes(association?.size))}</strong></div>
                        <div><span class="muted-text">Updated</span><strong>${escape(association?.updatedAt || 'Unknown')}</strong></div>
                    </div>
                    <h4>Asset Administration Shells</h4>
                    ${renderIds(shellIds, 'No shell IDs recorded.')}
                    <h4>Submodels</h4>
                    ${renderIds(submodelIds, 'No submodel IDs recorded.')}
                `;
            }
            if (fields.viewDownload) {
                fields.viewDownload.href = association?.downloadUrl || associationUrl(labId, 'download');
                fields.viewDownload.hidden = false;
            }
            fields.viewModal.classList?.add('show');
        }

        async function viewPackage(labId) {
            const safeLabId = String(labId || '').trim();
            if (!safeLabId) return;
            try {
                const response = await fetchImpl(associationUrl(safeLabId, 'view'));
                if (response.status === 404) {
                    showToast(`No AAS association configured for laboratory ${safeLabId}`, 'info');
                    return;
                }
                if (!response.ok) throw new Error(await responseError(response));
                const association = await response.json();
                renderView(association);
                showToast(`AAS association loaded for laboratory ${safeLabId}`, 'success');
            } catch (error) {
                logger.error(error);
                showToast(`AAS association view failed: ${error.message}`, 'error');
            }
        }

        async function deletePackage(labId, button = null) {
            const safeLabId = String(labId || '').trim();
            const association = associations.find(item => String(item?.labId || '').trim() === safeLabId);
            const isLinked = String(association?.source || '').trim().toLowerCase() === 'linked';
            const removalEffect = isLinked
                ? 'This removes only the link.'
                : 'This deletes its BaSyx resources.';
            if (!safeLabId || !confirmImpl(`Remove the AAS association for laboratory ${safeLabId}? ${removalEffect}`)) return;
            if (button) button.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/aas/${encodeURIComponentImpl(safeLabId)}`, { method: 'DELETE' });
                if (response.status === 404) {
                    showToast(`No AAS association configured for laboratory ${safeLabId}`, 'info');
                    return;
                }
                if (!response.ok) throw new Error(await responseError(response));
                associations = associations.filter(item => String(item?.labId || '').trim() !== safeLabId);
                renderPackageList();
                setStatus(associations.length ? `${associations.length} AAS association${associations.length === 1 ? '' : 's'} registered.` : 'No AAS associations registered.');
                showToast(`${isLinked ? 'AAS link removed' : 'AAS association removed'} for laboratory ${safeLabId}`, 'success');
            } catch (error) {
                logger.error(error);
                showToast(`AAS association removal failed: ${error.message}`, 'error');
            } finally {
                if (button) button.disabled = false;
            }
        }

        function closeView() {
            fields.viewModal?.classList?.remove('show');
        }

        function bind() {
            if (bound) return;
            bound = true;
            fields.refreshButton?.addEventListener('click', () => void loadPackages({ notifyError: true }));
            fields.viewClose?.addEventListener('click', closeView);
            fields.viewCloseFooter?.addEventListener('click', closeView);
            fields.viewModal?.addEventListener('click', event => {
                if (event.target === fields.viewModal) closeView();
            });
            fields.packageList?.addEventListener('click', event => {
                const viewButton = event.target?.closest?.('[data-aasx-view]');
                if (viewButton) {
                    void viewPackage(viewButton.dataset.aasxView);
                    return;
                }
                const deleteButton = event.target?.closest?.('[data-aasx-delete]');
                if (deleteButton) void deletePackage(deleteButton.dataset.aasxDelete, deleteButton);
            });
        }

        function initialize() {
            bind();
            renderPackageList();
        }

        return Object.freeze({
            clearPackages,
            closeView,
            deletePackage,
            getPackages: () => associations.map(association => ({ ...association })),
            initialize,
            loadPackages,
            setManagedLabs: labs => {
                managedLabs = Array.isArray(labs) ? [...labs] : [];
                renderPackageList();
            },
            viewPackage,
        });
    }

    root.LabManagerAasx = Object.freeze({ createController });
}(window));
