(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        showOpsWarning,
        getControllers = () => [],
        getManagedLabs = () => [],
        resolveLabDisplayName,
        renderPowerPolicyStepsMarkup = () => '',
        createPowerPolicyStepDraft,
        parsePowerPolicyInteger,
        logger = console,
        documentImpl = typeof document === 'undefined' ? null : document,
    }) {
        let powerPolicies = [];
        let powerPolicyStepDrafts = [];
        let draggedStepIndex = -1;
        let draggedRow = null;
        let dragOverRow = null;

        function renderSteps() {
            if (!fields.steps) return;
            fields.steps.innerHTML = renderPowerPolicyStepsMarkup(
                powerPolicyStepDrafts,
                getControllers(),
            );
        }

        function resetEditor(clearLabId = true) {
            if (clearLabId && fields.labSelect) fields.labSelect.value = '';
            if (fields.name) fields.name.value = 'New lab policy';
            if (fields.enabled) fields.enabled.checked = true;
            if (fields.respectLocalMode) fields.respectLocalMode.checked = true;
            if (fields.maintenanceMode) fields.maintenanceMode.checked = false;
            if (fields.startFailureMode) fields.startFailureMode.value = 'fail_reservation_start';
            if (fields.endFailureMode) fields.endFailureMode.value = 'warn_and_continue';
            powerPolicyStepDrafts = [];
            renderSteps();
            if (fields.editorHint) fields.editorHint.textContent = '';
        }

        function populateForm(policy) {
            if (fields.name) fields.name.value = policy.policyName || '';
            if (fields.enabled) fields.enabled.checked = policy.enabled !== false;
            if (fields.respectLocalMode) fields.respectLocalMode.checked = policy.respectLocalMode !== false;
            if (fields.maintenanceMode) fields.maintenanceMode.checked = policy.maintenanceMode === true;
            if (fields.startFailureMode) fields.startFailureMode.value = policy.startFailureMode || 'fail_reservation_start';
            if (fields.endFailureMode) fields.endFailureMode.value = policy.endFailureMode || 'warn_and_continue';
            powerPolicyStepDrafts = Array.isArray(policy.steps)
                ? policy.steps.map(createPowerPolicyStepDraft)
                : [];
            renderSteps();
        }

        function getStepIndex(target) {
            const row = target?.closest?.('[data-step-index]');
            const index = Number.parseInt(row?.dataset?.stepIndex, 10);
            return Number.isInteger(index) && index >= 0 && index < powerPolicyStepDrafts.length ? index : -1;
        }

        function clearDragState() {
            draggedRow?.classList?.remove('is-dragging');
            dragOverRow?.classList?.remove('is-drag-over');
            draggedRow = null;
            dragOverRow = null;
            draggedStepIndex = -1;
        }

        function handleStepDragStart(event) {
            const index = getStepIndex(event.target);
            if (index < 0) return;
            draggedStepIndex = index;
            draggedRow = event.target?.closest?.('[data-step-index]') || null;
            event.dataTransfer?.setData?.('text/plain', String(index));
            if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
            draggedRow?.classList?.add('is-dragging');
        }

        function handleStepDragOver(event) {
            if (draggedStepIndex < 0) return;
            const row = event.target?.closest?.('[data-step-index]');
            const index = getStepIndex(event.target);
            if (!row || index < 0) return;
            event.preventDefault();
            if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
            if (dragOverRow !== row) {
                dragOverRow?.classList?.remove('is-drag-over');
                dragOverRow = row;
                dragOverRow.classList?.add('is-drag-over');
            }
        }

        function handleStepDrop(event) {
            const targetIndex = getStepIndex(event.target);
            const transferredIndex = Number.parseInt(event.dataTransfer?.getData?.('text/plain'), 10);
            const sourceIndex = Number.isInteger(transferredIndex) ? transferredIndex : draggedStepIndex;
            if (sourceIndex < 0 || sourceIndex >= powerPolicyStepDrafts.length || targetIndex < 0) return;
            event.preventDefault();
            if (sourceIndex !== targetIndex) {
                const [movedStep] = powerPolicyStepDrafts.splice(sourceIndex, 1);
                const insertionIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
                powerPolicyStepDrafts.splice(insertionIndex, 0, movedStep);
            }
            clearDragState();
            renderSteps();
        }

        function handleStepDragEnd() {
            clearDragState();
        }

        function handleStepChange(event) {
            const field = event.target?.dataset?.stepField;
            if (!field) return;
            const index = getStepIndex(event.target);
            if (index < 0) return;
            const step = powerPolicyStepDrafts[index];
            step[field] = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
            if (field === 'phase') {
                step.phase = String(event.target.value || '').trim().toLowerCase();
            } else if (field === 'controllerId') {
                step.outlet = '';
                renderSteps();
            } else if (field === 'action') {
                renderSteps();
            }
        }

        function handleStepActions(event) {
            const button = event.target?.closest?.('[data-step-action]');
            if (!button || button.dataset.stepAction !== 'remove') return;
            const index = getStepIndex(button);
            if (index < 0) return;
            powerPolicyStepDrafts.splice(index, 1);
            renderSteps();
        }

        function addStep() {
            const firstController = getControllers()[0];
            const firstOutlet = Array.isArray(firstController?.outlets) ? firstController.outlets[0] : null;
            powerPolicyStepDrafts.push(createPowerPolicyStepDraft({
                phase: 'pre_start',
                controllerId: firstController?.id || '',
                outlet: firstOutlet?.outlet || '',
            }));
            renderSteps();
        }

        function readForm() {
            const policyName = (fields.name?.value || '').trim();
            if (!policyName) throw new Error('Policy name is required');
            const steps = powerPolicyStepDrafts.map((step, index) => {
                if (!step.phase) throw new Error(`Step ${index + 1}: phase is required`);
                if (!step.controllerId) throw new Error(`Step ${index + 1}: select a controller`);
                if (!step.outlet) throw new Error(`Step ${index + 1}: select an outlet`);
                if (!['pre_start', 'start', 'post_start', 'pre_end', 'end', 'post_end', 'manual', 'maintenance', 'emergency_stop'].includes(step.phase)) {
                    throw new Error(`Step ${index + 1}: unsupported phase`);
                }
                if (!['on', 'off', 'cycle'].includes(step.action)) {
                    throw new Error(`Step ${index + 1}: unsupported action`);
                }
                let conditions = {};
                if (step.conditionsText?.trim()) {
                    try {
                        conditions = JSON.parse(step.conditionsText);
                    } catch (error) {
                        throw new Error(`Step ${index + 1}: conditions JSON is invalid`);
                    }
                    if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) {
                        throw new Error(`Step ${index + 1}: conditions must be an object`);
                    }
                }
                const normalized = {
                    phase: step.phase,
                    controllerId: step.controllerId,
                    outlet: step.outlet,
                    action: step.action,
                    required: step.required === true,
                    readBackRequired: step.readBackRequired === true,
                    delayBeforeSeconds: parsePowerPolicyInteger(step.delayBeforeSeconds, 'Delay before', 3600),
                    delayAfterSeconds: parsePowerPolicyInteger(step.delayAfterSeconds, 'Delay after', 3600),
                    timeoutSeconds: parsePowerPolicyInteger(step.timeoutSeconds, 'Timeout', 300),
                    retryCount: parsePowerPolicyInteger(step.retryCount, 'Retries', 5),
                    allowProtected: step.allowProtected === true,
                    conditions,
                };
                if (step.action === 'cycle') {
                    const offSeconds = parsePowerPolicyInteger(step.offSeconds, 'Cycle off time', 3600);
                    if (offSeconds === 0) {
                        throw new Error(`Step ${index + 1}: cycle off time must be greater than zero`);
                    }
                    normalized.offSeconds = offSeconds;
                }
                if (step.id) normalized.id = step.id;
                if (step.stepLabel) normalized.stepLabel = step.stepLabel;
                return normalized;
            });
            return {
                policyName,
                enabled: fields.enabled?.checked !== false,
                respectLocalMode: fields.respectLocalMode?.checked !== false,
                maintenanceMode: fields.maintenanceMode?.checked === true,
                startFailureMode: fields.startFailureMode?.value || 'fail_reservation_start',
                endFailureMode: fields.endFailureMode?.value || 'warn_and_continue',
                steps,
            };
        }

        function renderOptions(preferredLabId) {
            if (!fields.select) return;
            const current = fields.select.value;
            fields.select.innerHTML = '<option value="">New policy</option>';
            powerPolicies.forEach(policy => {
                const option = documentImpl?.createElement('option') || { dataset: {} };
                option.value = policy.labId || '';
                const labs = getManagedLabs();
                const lab = labs.find(item => String(item?.labId || '') === String(policy.labId || ''))
                    || { labId: policy.labId };
                option.textContent = `${resolveLabDisplayName(lab)} · ${policy.policyName || 'Unnamed policy'}`;
                fields.select.appendChild(option);
            });
            const selected = preferredLabId || current;
            if (selected && powerPolicies.some(policy => String(policy.labId) === selected)) {
                fields.select.value = selected;
            } else {
                fields.select.value = '';
            }
            loadSelected();
        }

        function loadSelected() {
            const labId = fields.select?.value || '';
            const policy = powerPolicies.find(item => String(item.labId || '') === labId);
            if (policy) {
                if (fields.labSelect) fields.labSelect.value = policy.labId || '';
                populateForm(policy);
                return;
            }
            resetEditor(false);
        }

        function handleLabChange() {
            const labId = fields.labSelect?.value || '';
            if (fields.select) {
                fields.select.value = powerPolicies.some(policy => String(policy.labId || '') === labId)
                    ? labId
                    : '';
            }
            loadSelected();
        }

        async function load(options = {}) {
            if (fields.status) {
                fields.status.textContent = 'Loading...';
                fields.status.className = 'pill soft';
            }
            try {
                const selectedLabId = fields.labSelect?.value || fields.select?.value || '';
                const response = await fetchImpl('/ops/api/power/policies', options);
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) {
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power policies', 'error');
                    return;
                }
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                powerPolicies = Array.isArray(body.policies) ? body.policies : [];
                renderOptions(selectedLabId);
                if (fields.status) {
                    fields.status.textContent = `${powerPolicies.length} polic${powerPolicies.length === 1 ? 'y' : 'ies'}`;
                    fields.status.className = 'pill good';
                }
            } catch (error) {
                logger.warn('Unable to load power policies', error);
                powerPolicies = [];
                renderOptions('');
                if (fields.status) {
                    fields.status.textContent = 'Unavailable';
                    fields.status.className = 'pill bad';
                }
                if (fields.editorHint) fields.editorHint.textContent = 'Power policies could not be loaded.';
            }
        }

        async function save() {
            const labId = fields.labSelect?.value || '';
            if (!labId) {
                showToast('Select a laboratory before saving the policy', 'error');
                return;
            }
            let policy;
            try {
                policy = readForm();
            } catch (error) {
                showToast(`Power policy is invalid: ${error.message}`, 'error');
                return;
            }
            policy.labId = labId;
            delete policy.lab_id;
            if (fields.saveButton) fields.saveButton.disabled = true;
            try {
                const response = await fetchImpl(`/ops/api/power/policies/${encodeURIComponent(labId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(policy),
                });
                const body = await response.json().catch(() => ({}));
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) throw new Error('Lab Manager session required');
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                showToast(`Power policy for ${labId} saved`, 'success');
                await load({ skipAuthPrompt: true });
                if (fields.select) fields.select.value = labId;
                loadSelected();
            } catch (error) {
                showToast(`Power policy save failed: ${error.message}`, 'error');
            } finally {
                if (fields.saveButton) fields.saveButton.disabled = false;
            }
        }

        function initialize() {
            fields.select?.addEventListener('change', loadSelected);
            fields.labSelect?.addEventListener('change', handleLabChange);
            fields.addStep?.addEventListener('click', addStep);
            fields.steps?.addEventListener('change', handleStepChange);
            fields.steps?.addEventListener('input', handleStepChange);
            fields.steps?.addEventListener('click', handleStepActions);
            fields.steps?.addEventListener('dragstart', handleStepDragStart);
            fields.steps?.addEventListener('dragover', handleStepDragOver);
            fields.steps?.addEventListener('drop', handleStepDrop);
            fields.steps?.addEventListener('dragend', handleStepDragEnd);
            fields.saveButton?.addEventListener('click', save);
            if (fields.name && !fields.name.value) resetEditor();
        }

        return Object.freeze({
            addStep,
            getPolicies: () => powerPolicies,
            getStepDrafts: () => powerPolicyStepDrafts,
            handleLabChange,
            handleStepChange,
            handleStepActions,
            handleStepDragEnd,
            handleStepDragOver,
            handleStepDragStart,
            handleStepDrop,
            initialize,
            load,
            loadSelected,
            populateForm,
            readForm,
            renderOptions,
            renderSteps,
            resetEditor,
            save,
        });
    }

    root.LabManagerPowerPolicies = Object.freeze({ createController });
})(window);
