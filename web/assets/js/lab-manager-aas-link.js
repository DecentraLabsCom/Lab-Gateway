(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        encodeURIComponentImpl = encodeURIComponent,
    }) {
        function selectedOption() {
            const selectedValue = (fields.keyInput && fields.keyInput.value || '').trim();
            return Array.from(fields.keyInput?.options || [])
                .find(candidate => String(candidate.value || '') === selectedValue);
        }

        function selectedLabId() {
            const selectedValue = (fields.keyInput && fields.keyInput.value || '').trim();
            const option = selectedOption();
            return String(option?.dataset?.labId || selectedValue).trim();
        }

        function renderAccessPolicyStatus(status, fallbackMessage = '') {
            const panel = fields.accessPolicyStatus;
            if (!panel) return;
            const state = String(status?.state || 'unavailable');
            const messages = {
                generated: 'Gateway-generated AAS access rules are active.',
                customized: 'Provider-defined AAS access rules are active.',
                stale: 'The AAS access rules do not match the current FMU interface. Update or regenerate the rules.',
                invalid: 'The AAS access rules are invalid or refer to variables that do not match this FMU.',
                'fmi-default': status?.aasLinked
                    ? 'The linked AAS has no compatible variable access policy; FMI-derived defaults are active.'
                    : 'No AAS access policy is linked; FMI-derived defaults are active.',
                unavailable: 'The linked AAS or its access rules could not be verified.',
                not_checked: 'Select or check an FMU link to validate its variable access rules.',
            };
            const warning = ['stale', 'invalid', 'unavailable'].includes(state)
                || (state === 'fmi-default' && status?.aasLinked === true);
            panel.hidden = false;
            panel.dataset.state = state;
            panel.dataset.status = warning ? 'warning' : state === 'not_checked' ? 'not_checked' : 'passed';
            panel.textContent = String(status?.message || fallbackMessage || messages[state] || messages.unavailable);
            if (Number.isFinite(Number(status?.readableVariableCount))) {
                panel.textContent += ` Readable variables: ${Number(status.readableVariableCount)}; writable variables: ${Number(status.writableVariableCount || 0)}.`;
            }
        }

        function reportLinkFailure(action, error) {
            if (Number(selectedOption()?.dataset?.resourceType) !== 1) return;
            renderAccessPolicyStatus(
                { state: 'unavailable' },
                `Could not ${action} this FMU's AAS link, so its access rules were not verified. ${error.message}`,
            );
        }

        async function loadAccessPolicyStatus() {
            const panel = fields.accessPolicyStatus;
            if (!panel) return null;
            const option = selectedOption();
            const labId = selectedLabId();
            if (!labId || Number(option?.dataset?.resourceType) !== 1) {
                renderAccessPolicyStatus({
                    state: 'not_checked',
                    message: labId ? 'Variable access validation applies to FMU laboratories.' : undefined,
                });
                return null;
            }
            const accessKey = String(option?.dataset?.accessKey || option?.value || '').trim();
            if (!accessKey) {
                renderAccessPolicyStatus({ state: 'unavailable' }, 'This FMU has no Gateway access key, so its AAS rules could not be checked.');
                return null;
            }
            renderAccessPolicyStatus({ state: 'not_checked' }, 'Checking the linked AAS access rules…');
            try {
                const response = await fetchImpl(
                    `/aas-admin/fmu/${encodeURIComponentImpl(accessKey)}/access-policy?labId=${encodeURIComponentImpl(labId)}`,
                );
                const status = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(status.detail || `HTTP ${response.status}`);
                renderAccessPolicyStatus(status);
                return status;
            } catch (error) {
                renderAccessPolicyStatus(
                    { state: 'unavailable' },
                    `Could not verify this FMU's AAS access rules: ${error.message}`,
                );
                return null;
            }
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
                const accessPolicySubmodelId = (fields.accessPolicySubmodelIdInput?.value || '').trim();
                if (accessPolicySubmodelId) payload.accessControlSubmodelId = accessPolicySubmodelId;
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
                await loadAccessPolicyStatus();
            } catch (error) {
                reportLinkFailure('save', error);
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
                    if (fields.accessPolicySubmodelIdInput) fields.accessPolicySubmodelIdInput.value = '';
                    await loadAccessPolicyStatus();
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (fields.aasIdInput) fields.aasIdInput.value = data.aasId || '';
                if (fields.accessPolicySubmodelIdInput) {
                    fields.accessPolicySubmodelIdInput.value = data.accessControlSubmodelId || '';
                }
                showToast(`AAS link checked for laboratory ${labId}: ${data.aasId}`, 'success');
                await loadAccessPolicyStatus();
            } catch (error) {
                reportLinkFailure('check', error);
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
                    if (fields.aasIdInput) fields.aasIdInput.value = '';
                    if (fields.accessPolicySubmodelIdInput) fields.accessPolicySubmodelIdInput.value = '';
                    await loadAccessPolicyStatus();
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                if (fields.aasIdInput) fields.aasIdInput.value = '';
                if (fields.accessPolicySubmodelIdInput) fields.accessPolicySubmodelIdInput.value = '';
                showToast(`AAS link removed for laboratory ${labId}`, 'success');
                await loadAccessPolicyStatus();
            } catch (error) {
                reportLinkFailure('remove', error);
                showToast(`Remove link failed: ${error.message}`, 'error');
            } finally {
                fields.deleteButton.disabled = false;
            }
        }

        function initialize() {
            fields.saveButton?.addEventListener('click', saveLink);
            fields.checkButton?.addEventListener('click', checkLink);
            fields.deleteButton?.addEventListener('click', deleteLink);
            fields.keyInput?.addEventListener('change', () => { void loadAccessPolicyStatus(); });
        }

        return Object.freeze({
            checkLink,
            deleteLink,
            initialize,
            loadAccessPolicyStatus,
            saveLink,
        });
    }

    root.LabManagerAasLink = Object.freeze({ createController });
})(window);
