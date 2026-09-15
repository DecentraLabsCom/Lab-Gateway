(function (root) {
    'use strict';

    function createController({
        fields = {},
        hostMetadata = {},
        trustController,
        pollHeartbeat = async () => {},
        formatDate = value => String(value ?? ''),
        showToast = () => {},
        confirmImpl = message => root.confirm(message),
        documentImpl = root.document,
    } = {}) {
        if (!trustController) {
            throw new Error('LabManagerWinrmTrustModal requires trustController');
        }
        if (!documentImpl || typeof documentImpl.createElement !== 'function') {
            throw new Error('LabManagerWinrmTrustModal requires documentImpl');
        }

        const {
            modal,
            modalHost,
            current,
            certificate,
            certificateName,
            preview,
            previewDetails,
            fingerprintConfirmed,
            previewButton,
            saveButton,
            verifyButton,
            deleteButton,
        } = fields;
        let activeHost = '';
        let savedStatus = 'loading';
        let activeFile = null;
        let activePreview = null;

        function statusLabel(status) {
            const labels = {
                missing: 'missing',
                ready: 'ready',
                expired: 'expired',
                'not-yet-valid': 'not yet valid',
                invalid: 'invalid',
                unavailable: 'unavailable',
            };
            return labels[String(status || '').trim().toLowerCase()] || 'unavailable';
        }

        function statusClass(status) {
            const normalized = String(status || '').trim().toLowerCase();
            if (normalized === 'ready') return 'good';
            if (normalized === 'missing' || normalized === 'unavailable') return 'warn';
            return 'bad';
        }

        function appendDetail(container, label, value) {
            const item = documentImpl.createElement('div');
            item.className = 'certificate-detail';
            const labelEl = documentImpl.createElement('dt');
            labelEl.textContent = label;
            const valueEl = documentImpl.createElement('dd');
            valueEl.textContent = value === null || value === undefined || value === '' ? 'n/a' : String(value);
            item.append(labelEl, valueEl);
            container.appendChild(item);
        }

        function updateVerifyState() {
            if (!verifyButton) return;
            verifyButton.disabled = !(
                activeHost &&
                hostMetadata[activeHost]?.winrmConfigured === true &&
                savedStatus === 'ready'
            );
        }

        function updateSaveState() {
            if (previewButton) previewButton.disabled = !activeFile;
            if (saveButton) {
                saveButton.disabled = !(
                    activeFile &&
                    activePreview?.valid === true &&
                    fingerprintConfirmed?.checked === true
                );
            }
            updateVerifyState();
        }

        function renderState(trust) {
            const status = String(trust?.status || (trust?.configured ? 'ready' : 'missing'))
                .trim()
                .toLowerCase();
            savedStatus = status;
            updateVerifyState();
            if (!current) return;
            current.className = `winrm-trust-current ${statusClass(status)}`;
            current.replaceChildren();

            const title = documentImpl.createElement('strong');
            title.textContent = `Current trust: ${statusLabel(status)}`;
            current.appendChild(title);

            const details = documentImpl.createElement('dl');
            details.className = 'certificate-detail-grid';
            appendDetail(details, 'SHA-256', trust?.fingerprintSha256);
            appendDetail(details, 'SHA-1', trust?.fingerprintSha1);
            appendDetail(details, 'Subject', trust?.subject);
            appendDetail(details, 'SAN DNS', Array.isArray(trust?.sanDnsNames) ? trust.sanDnsNames.join(', ') : '');
            appendDetail(details, 'SAN IP', Array.isArray(trust?.sanIpAddresses) ? trust.sanIpAddresses.join(', ') : '');
            appendDetail(details, 'Valid until', trust?.notAfter ? formatDate(trust.notAfter) : '');
            appendDetail(details, 'Last validated', trust?.lastValidatedAt ? formatDate(trust.lastValidatedAt) : '');
            appendDetail(details, 'Error code', trust?.errorCode);
            current.appendChild(details);
        }

        function renderPreview(nextPreview) {
            activePreview = nextPreview;
            if (!preview || !previewDetails) return;
            preview.hidden = !nextPreview;
            previewDetails.replaceChildren();
            if (!nextPreview) {
                updateSaveState();
                return;
            }

            appendDetail(previewDetails, 'Status', statusLabel(nextPreview.status));
            appendDetail(previewDetails, 'SHA-256', nextPreview.fingerprintSha256);
            appendDetail(previewDetails, 'SHA-1', nextPreview.fingerprintSha1);
            appendDetail(previewDetails, 'Subject', nextPreview.subject);
            appendDetail(previewDetails, 'Issuer', nextPreview.issuer);
            appendDetail(previewDetails, 'SAN DNS', Array.isArray(nextPreview.sanDnsNames) ? nextPreview.sanDnsNames.join(', ') : '');
            appendDetail(previewDetails, 'SAN IP', Array.isArray(nextPreview.sanIpAddresses) ? nextPreview.sanIpAddresses.join(', ') : '');
            appendDetail(previewDetails, 'Valid from', nextPreview.notBefore ? formatDate(nextPreview.notBefore) : '');
            appendDetail(previewDetails, 'Valid until', nextPreview.notAfter ? formatDate(nextPreview.notAfter) : '');
            appendDetail(previewDetails, 'Format', nextPreview.format);
            if (fingerprintConfirmed) fingerprintConfirmed.checked = false;
            updateSaveState();
        }

        function handleCertificateSelected() {
            activeFile = certificate?.files?.[0] || null;
            activePreview = null;
            if (certificateName) {
                certificateName.textContent = activeFile?.name || 'No file selected';
            }
            renderPreview(null);
            updateSaveState();
        }

        async function open(host) {
            if (!modal || !certificate) {
                showToast('WinRM TLS trust modal is unavailable', 'error');
                return;
            }
            activeHost = host;
            savedStatus = 'loading';
            activeFile = null;
            activePreview = null;
            certificate.value = '';
            if (certificateName) certificateName.textContent = 'No file selected';
            if (modalHost) {
                const meta = hostMetadata[host] || {};
                modalHost.textContent = `Host: ${host} · Address: ${meta.address || 'n/a'}`;
            }
            if (fingerprintConfirmed) fingerprintConfirmed.checked = false;
            renderPreview(null);
            if (current) current.textContent = 'Loading certificate trust state...';
            updateSaveState();
            modal.classList.add('show');
            await load(host);
        }

        async function load(host) {
            return trustController.load(host);
        }

        function close() {
            if (modal) modal.classList.remove('show');
            activeHost = '';
            savedStatus = 'unavailable';
            activeFile = null;
            activePreview = null;
            updateSaveState();
        }

        function markUnavailable() {
            savedStatus = 'unavailable';
            updateVerifyState();
        }

        async function previewCertificate() {
            if (!activeHost || !activeFile) {
                showToast('Choose a station certificate first', 'error');
                return;
            }
            if (previewButton) previewButton.disabled = true;
            await trustController.preview(activeHost, activeFile);
        }

        async function save() {
            if (!activeHost || !activeFile || activePreview?.valid !== true) {
                showToast('Preview a valid certificate first', 'error');
                return;
            }
            if (!fingerprintConfirmed?.checked) {
                showToast('Verify the SHA-256 fingerprint before saving', 'error');
                return;
            }
            if (saveButton) saveButton.disabled = true;
            await trustController.save(activeHost, activeFile, activePreview);
        }

        async function verify() {
            if (!activeHost || verifyButton?.disabled) return;
            await pollHeartbeat(activeHost);
        }

        async function remove() {
            if (!activeHost) return;
            if (!confirmImpl(`Remove WinRM TLS trust for ${activeHost}?`)) return;
            if (deleteButton) deleteButton.disabled = true;
            await trustController.remove(activeHost);
        }

        function getState() {
            return {
                activeHost,
                savedStatus,
                activeFile,
                activePreview,
            };
        }

        return Object.freeze({
            close,
            delete: remove,
            getState,
            handleCertificateSelected,
            load,
            markUnavailable,
            open,
            preview: previewCertificate,
            renderPreview,
            renderState,
            save,
            updateSaveState,
            updateVerifyState,
            verify,
        });
    }

    root.LabManagerWinrmTrustModal = Object.freeze({ createController });
})(window);
