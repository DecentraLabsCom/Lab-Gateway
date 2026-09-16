(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        encodeURIComponentImpl = encodeURIComponent,
    }) {
        function selectedLabId() {
            const selectedValue = (fields.keyInput && fields.keyInput.value || '').trim();
            const option = Array.from(fields.keyInput?.options || [])
                .find(candidate => String(candidate.value || '') === selectedValue);
            return String(option?.dataset?.labId || selectedValue).trim();
        }

        async function saveLink() {
            const labId = selectedLabId();
            const aasId = (fields.aasIdInput && fields.aasIdInput.value || '').trim();
            if (!labId) {
                showToast('Select a laboratory', 'error');
                return;
            }
            if (!aasId) {
                showToast('Enter an external AAS ID', 'error');
                return;
            }
            fields.saveButton.disabled = true;
            try {
                const payload = { aasId };
                const response = await fetchImpl(`/aas-admin/lab/${encodeURIComponentImpl(labId)}/aas-link`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const body = await response.json().catch(() => ({}));
                    throw new Error(body.detail || `HTTP ${response.status}`);
                }
                await response.json();
                showToast(`AAS link saved for laboratory ${labId}`, 'success');
            } catch (error) {
                showToast(`AAS link failed: ${error.message}`, 'error');
            } finally {
                fields.saveButton.disabled = false;
            }
        }

        async function checkLink() {
            const labId = selectedLabId();
            if (!labId) {
                showToast('Select a laboratory', 'error');
                return;
            }
            fields.checkButton.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/lab/${encodeURIComponentImpl(labId)}/aas-link`);
                if (response.status === 404) {
                    showToast(`No AAS link configured for laboratory ${labId}`, 'info');
                    if (fields.aasIdInput) fields.aasIdInput.value = '';
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (fields.aasIdInput) fields.aasIdInput.value = data.aasId || '';
                showToast(`AAS link checked for laboratory ${labId}: ${data.aasId}`, 'success');
            } catch (error) {
                showToast(`AAS link check failed: ${error.message}`, 'error');
            } finally {
                fields.checkButton.disabled = false;
            }
        }

        async function deleteLink() {
            const labId = selectedLabId();
            if (!labId) {
                showToast('Select a laboratory', 'error');
                return;
            }
            fields.deleteButton.disabled = true;
            try {
                const response = await fetchImpl(`/aas-admin/lab/${encodeURIComponentImpl(labId)}/aas-link`, {
                    method: 'DELETE',
                });
                if (response.status === 404) {
                    showToast(`No AAS link configured for laboratory ${labId}`, 'info');
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                if (fields.aasIdInput) fields.aasIdInput.value = '';
                showToast(`AAS link removed for laboratory ${labId}`, 'success');
            } catch (error) {
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
