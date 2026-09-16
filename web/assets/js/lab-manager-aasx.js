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
        let packages = [];
        let bound = false;

        function packageUrl(labId, action) {
            return `/aas-admin/aas/${encodeURIComponentImpl(labId)}/${action}`;
        }

        function resolveLabName(labId) {
            const lab = managedLabs.find(candidate => String(candidate?.labId || '').trim() === labId);
            return lab ? String(resolveLabDisplayName(lab) || `Lab #${labId}`) : `Lab #${labId}`;
        }

        function formatBytes(value) {
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
            if (!packages.length) {
                target.innerHTML = '<div class="empty">No AASX associations registered.</div>';
                return;
            }

            target.innerHTML = `
                <table class="mini-table aasx-package-table">
                    <thead>
                        <tr>
                            <th>Laboratory</th>
                            <th>AASX association</th>
                            <th>Imported resources</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${packages.map(packageInfo => {
                            const labId = String(packageInfo?.labId || '').trim();
                            const filename = String(packageInfo?.filename || `${labId}.aasx`);
                            const downloadUrl = packageInfo?.downloadUrl || packageUrl(labId, 'download');
                            const shellCount = Array.isArray(packageInfo?.shellIds) ? packageInfo.shellIds.length : 0;
                            const submodelCount = Array.isArray(packageInfo?.submodelIds) ? packageInfo.submodelIds.length : 0;
                            return `
                                <tr>
                                    <td>
                                        <strong>${escape(resolveLabName(labId))}</strong>
                                        <div class="muted-text">Lab #${escape(labId)}</div>
                                    </td>
                                    <td>
                                        <code>${escape(filename)}</code>
                                        <div class="muted-text">${escape(formatBytes(packageInfo?.size))}</div>
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
                                            <i class="fas fa-trash" aria-hidden="true"></i> Delete
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
        }

        function clearPackages(message = 'No AASX associations registered.') {
            packages = [];
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
                    clearPackages('Lab Manager session required to load AASX packages.');
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load AASX packages', 'error');
                    return false;
                }
                if (response.status === 403) {
                    clearPackages('AASX package administration is unavailable in Lite mode.');
                    return false;
                }
                if (!response.ok) throw new Error(await responseError(response));
                const body = await response.json().catch(() => ({}));
                packages = Array.isArray(body.packages) ? body.packages : [];
                renderPackageList();
                setStatus(packages.length ? `${packages.length} AASX association${packages.length === 1 ? '' : 's'} registered.` : 'No AASX associations registered.');
                return true;
            } catch (error) {
                logger.warn('Unable to load AASX packages', error);
                clearPackages('Unable to load AASX packages.');
                if (options.notifyError) showToast(`AASX package load failed: ${error.message}`, 'error');
                return false;
            }
        }

        function renderView(packageInfo) {
            if (!fields.viewModal) return;
            const labId = String(packageInfo?.labId || '').trim();
            const filename = String(packageInfo?.filename || `${labId}.aasx`);
            const shellIds = Array.isArray(packageInfo?.shellIds) ? packageInfo.shellIds : [];
            const submodelIds = Array.isArray(packageInfo?.submodelIds) ? packageInfo.submodelIds : [];
            if (fields.viewTitle) fields.viewTitle.textContent = filename;
            if (fields.viewBody) {
                const renderIds = (ids, emptyLabel) => ids.length
                    ? `<ul>${ids.map(id => `<li><code>${escape(id)}</code></li>`).join('')}</ul>`
                    : `<p class="muted-text">${escape(emptyLabel)}</p>`;
                fields.viewBody.innerHTML = `
                    <div class="aasx-view-summary">
                        <div><span class="muted-text">Laboratory</span><strong>${escape(resolveLabName(labId))}</strong></div>
                        <div><span class="muted-text">Imported source size</span><strong>${escape(formatBytes(packageInfo?.size))}</strong></div>
                        <div><span class="muted-text">Updated</span><strong>${escape(packageInfo?.updatedAt || 'Unknown')}</strong></div>
                    </div>
                    <h4>Asset Administration Shells</h4>
                    ${renderIds(shellIds, 'No shell IDs recorded.')}
                    <h4>Submodels</h4>
                    ${renderIds(submodelIds, 'No submodel IDs recorded.')}
                `;
            }
            if (fields.viewDownload) {
                fields.viewDownload.href = packageInfo?.downloadUrl || packageUrl(labId, 'download');
                fields.viewDownload.hidden = false;
            }
            fields.viewModal.classList?.add('show');
        }

        async function viewPackage(labId) {
            const safeLabId = String(labId || '').trim();
            if (!safeLabId) return;
            try {
                const response = await fetchImpl(packageUrl(safeLabId, 'view'));
                if (response.status === 404) {
                    showToast(`No AASX package configured for laboratory ${safeLabId}`, 'info');
                    return;
                }
                if (!response.ok) throw new Error(await responseError(response));
                const packageInfo = await response.json();
                renderView(packageInfo);
                showToast(`AASX package loaded for laboratory ${safeLabId}`, 'success');
            } catch (error) {
                logger.error(error);
                showToast(`AASX package view failed: ${error.message}`, 'error');
            }
        }

        async function deletePackage(labId, button = null) {
            const safeLabId = String(labId || '').trim();
            if (!safeLabId || !confirmImpl(`Remove the AASX association for laboratory ${safeLabId}? This deletes its BaSyx resources.`)) return;
            if (button) button.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/aas/${encodeURIComponentImpl(safeLabId)}`, { method: 'DELETE' });
                if (response.status === 404) {
                    showToast(`No AASX package configured for laboratory ${safeLabId}`, 'info');
                    return;
                }
                if (!response.ok) throw new Error(await responseError(response));
                packages = packages.filter(packageInfo => String(packageInfo?.labId || '').trim() !== safeLabId);
                renderPackageList();
                setStatus(packages.length ? `${packages.length} AASX association${packages.length === 1 ? '' : 's'} registered.` : 'No AASX associations registered.');
                showToast(`AASX association removed for laboratory ${safeLabId}`, 'success');
            } catch (error) {
                logger.error(error);
                showToast(`AASX package removal failed: ${error.message}`, 'error');
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
            getPackages: () => packages.map(packageInfo => ({ ...packageInfo })),
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
