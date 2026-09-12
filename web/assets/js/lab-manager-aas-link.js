(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        encodeURIComponentImpl = encodeURIComponent,
    }) {
        function showResult(message, isError) {
            if (!fields.result) return;
            fields.result.textContent = message;
            fields.result.style.color = isError
                ? 'var(--color-error, #c0392b)'
                : 'var(--color-success, #1a7f4b)';
        }

        async function saveLink() {
            const accessKey = (fields.keyInput && fields.keyInput.value || '').trim();
            const labId = (fields.labSelect && fields.labSelect.value || '').trim();
            const aasId = (fields.aasIdInput && fields.aasIdInput.value || '').trim();
            if (!accessKey) {
                showToast('Enter an access key', 'error');
                return;
            }
            if (!aasId) {
                showToast('Enter an external AAS ID', 'error');
                return;
            }
            fields.saveButton.disabled = true;
            try {
                const payload = { aasId };
                if (labId) payload.labId = labId;
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/aas-link`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const body = await response.json().catch(() => ({}));
                    throw new Error(body.detail || `HTTP ${response.status}`);
                }
                const data = await response.json();
                showResult(`Linked: ${data.aasId}`, false);
                showToast(`AAS link saved for ${accessKey}`, 'success');
            } catch (error) {
                showResult(error.message, true);
                showToast(`AAS link failed: ${error.message}`, 'error');
            } finally {
                fields.saveButton.disabled = false;
            }
        }

        async function checkLink() {
            const accessKey = (fields.keyInput && fields.keyInput.value || '').trim();
            if (!accessKey) {
                showToast('Enter an access key', 'error');
                return;
            }
            fields.checkButton.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/aas-link`);
                if (response.status === 404) {
                    showResult('No link configured for this access key.', false);
                    if (fields.aasIdInput) fields.aasIdInput.value = '';
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                showResult(`Current link: ${data.aasId}`, false);
                if (fields.aasIdInput) fields.aasIdInput.value = data.aasId || '';
                if (fields.labSelect) fields.labSelect.value = data.labId || '';
            } catch (error) {
                showResult(error.message, true);
            } finally {
                fields.checkButton.disabled = false;
            }
        }

        async function deleteLink() {
            const accessKey = (fields.keyInput && fields.keyInput.value || '').trim();
            if (!accessKey) {
                showToast('Enter an access key', 'error');
                return;
            }
            fields.deleteButton.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/aas-link`, {
                    method: 'DELETE',
                });
                if (response.status === 404) {
                    showResult('No link configured for this access key.', false);
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                showResult('Link removed.', false);
                if (fields.aasIdInput) fields.aasIdInput.value = '';
                showToast(`AAS link removed for ${accessKey}`, 'success');
            } catch (error) {
                showResult(error.message, true);
                showToast(`Remove link failed: ${error.message}`, 'error');
            } finally {
                fields.deleteButton.disabled = false;
            }
        }

        function initialize() {
            fields.saveButton?.addEventListener('click', saveLink);
            fields.checkButton?.addEventListener('click', checkLink);
            fields.deleteButton?.addEventListener('click', deleteLink);
        }

        return Object.freeze({
            checkLink,
            deleteLink,
            initialize,
            saveLink,
        });
    }

    root.LabManagerAasLink = Object.freeze({ createController });
})(window);
