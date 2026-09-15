(function (root) {
    'use strict';

    function createController({
        fields,
        fetchImpl,
        showToast,
        showOpsWarning,
        renderPolicySteps = () => {},
        renderControllerRowsMarkup = () => [],
        renderControllerCredentialOptionsMarkup = () => '',
        renderControllerOutletsMarkup = () => '',
        mergePowerControllerStatuses = (controllers) => controllers,
        createPowerControllerOutletDraft,
        buildPowerCommandPayload,
        logger = console,
        documentImpl = typeof document === 'undefined' ? null : document,
    }) {
        let powerControllers = [];
        let powerControllerStatusLoading = false;
        let powerControllerStatusError = false;
        let powerControllerStatusRequestId = 0;
        let powerControllerOutletDrafts = [];
        let powerControllerIdWasSuggested = false;
        let lastPowerControllerDriver = 'mock';
        let powerCredentials = [];
        let powerControllerEditorDirty = false;
        let powerControllerDeviceConfigurationDirty = false;

        function isDeviceController() {
            return ['apc-powernet-snmp', 'netio-json'].includes(fields.driver?.value || '');
        }

        function updateDriverFields() {
            const driver = fields.driver?.value || 'mock';
            powerControllerEditorDirty = true;
            const isNetio = driver === 'netio-json';
            const isApc = driver === 'apc-powernet-snmp';
            const currentPort = String(fields.port?.value || '');
            if (fields.port && driver === 'netio-json' && lastPowerControllerDriver !== 'netio-json' && currentPort === '161') {
                fields.port.value = fields.netioHttps?.checked === true ? '443' : '80';
            } else if (fields.port && driver !== 'netio-json' && lastPowerControllerDriver === 'netio-json' && ['80', '443'].includes(currentPort)) {
                fields.port.value = '161';
            }
            lastPowerControllerDriver = driver;
            if (fields.netioPathField) fields.netioPathField.hidden = !isNetio;
            if (fields.netioHttpsField) fields.netioHttpsField.hidden = !isNetio;
            if (fields.netioVerifyTlsField) fields.netioVerifyTlsField.hidden = !isNetio;
            if (fields.profileField) fields.profileField.hidden = !isApc;
        }

        function updateNetioPort() {
            if (fields.driver?.value !== 'netio-json' || !fields.port) return;
            powerControllerEditorDirty = true;
            if (['80', '443'].includes(String(fields.port.value || ''))) {
                fields.port.value = fields.netioHttps?.checked === true ? '443' : '80';
            }
        }

        function suggestId() {
            powerControllerEditorDirty = true;
            if (!fields.id || fields.select?.value) return;
            const host = String(fields.host?.value || '').trim().toLowerCase();
            if (!host) {
                if (powerControllerIdWasSuggested) {
                    fields.id.value = '';
                    powerControllerIdWasSuggested = false;
                }
                return;
            }
            const driver = fields.driver?.value || 'mock';
            const prefix = driver === 'apc-powernet-snmp'
                ? 'apc'
                : driver === 'netio-json'
                    ? 'netio'
                    : 'power';
            const hostSlug = host.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 110);
            if (!hostSlug) return;
            const suggestion = `${prefix}-${hostSlug}`;
            const current = String(fields.id.value || '').trim();
            if (!current || powerControllerIdWasSuggested) {
                fields.id.value = suggestion;
                powerControllerIdWasSuggested = true;
            }
        }

        function renderOutlets() {
            if (!fields.outlets) return;
            const drafts = isDeviceController() && !fields.select?.value
                ? powerControllerOutletDrafts.filter(outlet => outlet.deviceManaged === true)
                : powerControllerOutletDrafts;
            fields.outlets.innerHTML = renderControllerOutletsMarkup(drafts, {
                deviceManaged: isDeviceController(),
            });
            if (fields.addOutlet) fields.addOutlet.hidden = isDeviceController();
            if (fields.editorHint && isDeviceController()) {
                fields.editorHint.textContent = 'Physical output IDs and names come from the controller. APC device fields are written back on save; NETIO device fields are read-only here.';
            } else if (fields.editorHint) {
                fields.editorHint.textContent = '';
            }
        }

        function renderCredentialOptions() {
            if (!fields.credentialRef) return;
            const driver = fields.driver?.value || 'mock';
            const current = String(fields.credentialRef.value || '').trim();
            fields.credentialRef.innerHTML = renderControllerCredentialOptionsMarkup(
                driver,
                current,
                powerCredentials,
            );
            fields.credentialRef.value = current;
        }

        function resetEditor() {
            if (fields.select) fields.select.value = '';
            powerControllerIdWasSuggested = false;
            if (fields.id) {
                fields.id.value = '';
                fields.id.disabled = false;
            }
            if (fields.name) fields.name.value = '';
            if (fields.driver) fields.driver.value = 'mock';
            if (fields.enabled) fields.enabled.checked = true;
            if (fields.host) fields.host.value = '';
            if (fields.port) fields.port.value = '161';
            if (fields.credentialRef) fields.credentialRef.value = '';
            if (fields.netioPath) fields.netioPath.value = '/netio.json';
            if (fields.netioHttps) fields.netioHttps.checked = false;
            if (fields.netioVerifyTls) fields.netioVerifyTls.checked = true;
            if (fields.profile) fields.profile.value = 'auto';
            if (fields.timeoutSeconds) fields.timeoutSeconds.value = '2';
            if (fields.retries) fields.retries.value = '1';
            updateDriverFields();
            renderCredentialOptions();
            powerControllerOutletDrafts = [createPowerControllerOutletDraft({ outlet: '1' })];
            powerControllerEditorDirty = false;
            powerControllerDeviceConfigurationDirty = false;
            renderOutlets();
            if (fields.editorHint) fields.editorHint.textContent = '';
        }

        function populateForm(controller) {
            powerControllerIdWasSuggested = false;
            if (fields.id) {
                fields.id.value = controller.id || '';
                fields.id.disabled = true;
            }
            if (fields.name) fields.name.value = controller.name || '';
            if (fields.driver) fields.driver.value = controller.driver || 'mock';
            if (fields.enabled) fields.enabled.checked = controller.enabled !== false;
            if (fields.host) fields.host.value = controller.host || '';
            if (fields.credentialRef) fields.credentialRef.value = controller.credentialRef || '';
            const config = controller.config || {};
            const defaultPort = controller.driver === 'netio-json'
                ? (config.useHttps === true ? '443' : '80')
                : '161';
            if (fields.port) fields.port.value = controller.port || defaultPort;
            if (fields.netioPath) fields.netioPath.value = config.path || '/netio.json';
            if (fields.netioHttps) fields.netioHttps.checked = config.useHttps === true;
            if (fields.netioVerifyTls) fields.netioVerifyTls.checked = config.verifyTls !== false;
            if (fields.profile) fields.profile.value = config.profile || 'auto';
            if (fields.timeoutSeconds) fields.timeoutSeconds.value = config.timeoutSeconds || '2';
            if (fields.retries) fields.retries.value = config.retries ?? '1';
            updateDriverFields();
            renderCredentialOptions();
            powerControllerOutletDrafts = Array.isArray(controller.outlets)
                ? controller.outlets.map(createPowerControllerOutletDraft)
                : [];
            powerControllerEditorDirty = false;
            powerControllerDeviceConfigurationDirty = false;
            renderOutlets();
        }

        function renderOptions() {
            if (!fields.select) return;
            const current = fields.select.value;
            fields.select.innerHTML = '<option value="">New controller</option>';
            powerControllers.forEach(controller => {
                const option = documentImpl?.createElement('option') || { dataset: {} };
                option.value = controller.id || '';
                option.textContent = controller.name || controller.id || 'Unnamed controller';
                fields.select.appendChild(option);
            });
            const selected = powerControllers.some(controller => String(controller.id) === String(current)) ? current : '';
            fields.select.value = selected;
            if (selected) loadSelected();
            else resetEditor();
        }

        function setCredentials(credentials) {
            powerCredentials = Array.isArray(credentials) ? credentials : [];
            renderCredentialOptions();
        }

        function loadSelected() {
            const controllerId = fields.select?.value || '';
            const controller = powerControllers.find(item => String(item.id || '') === String(controllerId));
            if (controller) {
                populateForm(controller);
                return;
            }
            resetEditor();
        }

        function renderList() {
            if (!fields.list) return;
            fields.list.innerHTML = '';
            if (!powerControllers.length) {
                fields.list.innerHTML = '<div class="empty">No power controllers are configured.</div>';
                return;
            }
            const rows = renderControllerRowsMarkup(
                powerControllers,
                powerControllerStatusLoading,
                powerControllerStatusError,
            );
            rows.forEach(markup => {
                const row = documentImpl?.createElement('div') || { className: '', innerHTML: '' };
                row.className = 'power-controller-row';
                row.innerHTML = markup;
                fields.list.appendChild(row);
            });
        }

        function getOutletIndex(target) {
            const row = target?.closest?.('[data-controller-outlet-index]');
            const index = Number.parseInt(row?.dataset?.controllerOutletIndex, 10);
            return Number.isInteger(index) && index >= 0 && index < powerControllerOutletDrafts.length ? index : -1;
        }

        function handleOutletChange(event) {
            const deviceField = event.target?.dataset?.controllerDeviceConfigField;
            if (deviceField) {
                const index = getOutletIndex(event.target);
                if (index < 0) return;
                if (powerControllerOutletDrafts[index].deviceConfigWritable !== true) return;
                powerControllerOutletDrafts[index].deviceConfig[deviceField] = event.target.value;
                powerControllerEditorDirty = true;
                powerControllerDeviceConfigurationDirty = true;
                return;
            }
            const field = event.target?.dataset?.controllerOutletField;
            if (!field) return;
            const index = getOutletIndex(event.target);
            if (index < 0) return;
            powerControllerOutletDrafts[index][field] = event.target.type === 'checkbox'
                ? event.target.checked
                : event.target.value;
            powerControllerEditorDirty = true;
            if (field === 'deviceName') powerControllerDeviceConfigurationDirty = true;
        }

        function handleOutletActions(event) {
            const button = event.target?.closest?.('[data-controller-outlet-action]');
            if (!button || button.dataset.controllerOutletAction !== 'remove') return;
            const index = getOutletIndex(button);
            if (index < 0) return;
            powerControllerOutletDrafts.splice(index, 1);
            renderOutlets();
        }

        function addOutlet() {
            if (isDeviceController()) return;
            const usedIds = new Set(powerControllerOutletDrafts.map(outlet => outlet.outlet));
            let nextId = 1;
            while (usedIds.has(String(nextId))) nextId += 1;
            powerControllerOutletDrafts.push(createPowerControllerOutletDraft({ outlet: String(nextId) }));
            powerControllerEditorDirty = true;
            renderOutlets();
        }

        function readDeviceConfiguration() {
            if (!powerControllerDeviceConfigurationDirty) return undefined;
            const sourceOutlets = isDeviceController() && !fields.select?.value
                ? powerControllerOutletDrafts.filter(outlet => outlet.deviceManaged === true)
                : powerControllerOutletDrafts;
            const outlets = sourceOutlets.map((outlet, index) => {
                if (outlet.deviceConfigWritable !== true) return null;
                const outletId = String(outlet.outlet || '').trim();
                if (!outletId) throw new Error(`Output ${index + 1}: device ID is required`);
                const item = { outlet: outletId };
                if (Array.isArray(outlet.deviceConfigFields) && outlet.deviceConfigFields.includes('name')) {
                    if (String(outlet.deviceName || '').length > 160) throw new Error(`Output ${index + 1}: device name is too long`);
                    item.name = String(outlet.deviceName || '').trim();
                }
                const config = {};
                ['powerOnDelaySeconds', 'powerOffDelaySeconds', 'rebootDurationSeconds'].forEach(field => {
                    if (!Object.prototype.hasOwnProperty.call(outlet.deviceConfig || {}, field)) return;
                    const raw = outlet.deviceConfig[field];
                    if (raw === '' || raw === null || raw === undefined) return;
                    const value = Number.parseInt(raw, 10);
                    const minimum = field === 'rebootDurationSeconds' ? 5 : 0;
                    const maximum = field === 'rebootDurationSeconds' ? 60 : 7200;
                    if (!Number.isInteger(value) || value < minimum || value > maximum) {
                        throw new Error(`Output ${index + 1}: ${field} must be between ${minimum} and ${maximum}`);
                    }
                    config[field] = value;
                });
                if (Object.keys(config).length) item.config = config;
                return item;
            }).filter(Boolean);
            return { outlets };
        }

        function readForm() {
            const id = (fields.id?.value || '').trim();
            const name = (fields.name?.value || '').trim();
            const driver = (fields.driver?.value || '').trim();
            if (!id) throw new Error('Controller ID is required');
            if (!/^[A-Za-z0-9._:-]+$/.test(id)) throw new Error('Controller ID contains invalid characters');
            if (!name) throw new Error('Controller name is required');
            if (!['mock', 'apc-powernet-snmp', 'netio-json'].includes(driver)) throw new Error('Select a supported driver');
            const useHttps = fields.netioHttps?.checked === true;
            const defaultPort = driver === 'netio-json' ? (useHttps ? 443 : 80) : 161;
            const port = Number.parseInt(fields.port?.value || String(defaultPort), 10);
            if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Port must be between 1 and 65535');
            const timeoutSeconds = Number.parseInt(fields.timeoutSeconds?.value || '2', 10);
            if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 60) throw new Error('Timeout must be between 1 and 60 seconds');
            const retries = Number.parseInt(fields.retries?.value || '1', 10);
            if (!Number.isInteger(retries) || retries < 1 || retries > 10) throw new Error('Retries must be between 1 and 10');
            const host = (fields.host?.value || '').trim();
            const credentialRef = (fields.credentialRef?.value || '').trim();
            if (driver !== 'mock' && !host) throw new Error('Host is required for this driver');
            if (driver === 'apc-powernet-snmp' && !credentialRef) throw new Error('Credential reference is required for APC SNMP');

            const outlets = powerControllerOutletDrafts.map((outlet, index) => {
                const outletId = String(outlet.outlet || '').trim();
                if (!outletId) throw new Error(`Outlet ${index + 1}: ID is required`);
                const local = {
                    outlet: outletId,
                    logicalName: outlet.logicalName || '',
                    protected: outlet.protected === true,
                    critical: outlet.critical === true,
                    defaultState: outlet.defaultState === 'on' ? 'on' : 'off',
                };
                if (!isDeviceController()) local.displayName = outlet.displayName || '';
                return local;
            });
            if (!isDeviceController() && !outlets.length) throw new Error('At least one outlet is required');
            if (new Set(outlets.map(outlet => outlet.outlet)).size !== outlets.length) throw new Error('Outlet IDs must be unique');

            const config = driver === 'netio-json'
                ? {
                    path: (fields.netioPath?.value || '/netio.json').trim(),
                    useHttps,
                    verifyTls: fields.netioVerifyTls?.checked !== false,
                    timeoutSeconds,
                    retries,
                }
                : {
                    profile: fields.profile?.value || 'auto',
                    timeoutSeconds,
                    retries,
                };
            if (driver === 'netio-json' && (!config.path || !config.path.startsWith('/') || config.path.includes('\n') || config.path.includes('\r'))) {
                throw new Error('NETIO API path must start with /');
            }
            const controller = {
                id,
                name,
                driver,
                enabled: fields.enabled?.checked !== false,
                host,
                port,
                credentialRef,
                config,
                outlets,
            };
            const deviceConfiguration = isDeviceController() ? readDeviceConfiguration() : undefined;
            if (deviceConfiguration) controller.deviceConfiguration = deviceConfiguration;
            return controller;
        }

        async function save() {
            let controller;
            try {
                controller = readForm();
            } catch (error) {
                showToast(`Power controller is invalid: ${error.message}`, 'error');
                return;
            }
            const existingId = fields.select?.value || '';
            const method = existingId ? 'PUT' : 'POST';
            const url = existingId
                ? `/ops/api/power/controllers/${encodeURIComponent(existingId)}`
                : '/ops/api/power/controllers';
            if (fields.saveButton) fields.saveButton.disabled = true;
            try {
                const response = await fetchImpl(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(controller),
                });
                const body = await response.json().catch(() => ({}));
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) throw new Error('Lab Manager session required');
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                showToast(`Power controller ${controller.id} saved`, 'success');
                await load({ skipAuthPrompt: true, forceStatusRefresh: true });
                if (fields.select) fields.select.value = controller.id;
                loadSelected();
            } catch (error) {
                showToast(`Power controller save failed: ${error.message}`, 'error');
            } finally {
                if (fields.saveButton) fields.saveButton.disabled = false;
            }
        }

        async function handleActions(event) {
            const button = event.target.closest('[data-power-action]');
            if (!button) return;
            const action = button.dataset.powerAction;
            const controllerId = button.dataset.controllerId;
            const outletId = button.dataset.outletId;
            const protectedOutlet = button.dataset.protected === 'true';
            if (protectedOutlet && !fields.maintenanceMode?.checked) {
                showToast('Enable maintenance mode before operating a protected outlet', 'error');
                return;
            }
            const offSeconds = Number.parseInt(fields.cycleSeconds?.value || '10', 10);
            if (action === 'cycle' && (!Number.isInteger(offSeconds) || offSeconds < 1 || offSeconds > 3600)) {
                showToast('Cycle off time must be between 1 and 3600 seconds', 'error');
                return;
            }
            button.disabled = true;
            try {
                const payload = buildPowerCommandPayload(action, {
                    reason: fields.operationReason?.value.trim(),
                    idempotencyKey: createPowerIdempotencyKey(),
                    offSeconds,
                    protectedOutlet,
                    maintenance: fields.maintenanceMode?.checked === true,
                });
                const response = await fetchImpl(
                    `/ops/api/power/controllers/${encodeURIComponent(controllerId)}/outlets/${encodeURIComponent(outletId)}/commands`,
                    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
                );
                const body = await response.json().catch(() => ({}));
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) throw new Error('Lab Manager session required');
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                showToast(`Power ${action} completed for outlet ${outletId}`, 'success');
                void loadStatuses({ forceRefresh: true, skipAuthPrompt: true });
            } catch (error) {
                showToast(`Power ${action} failed: ${error.message}`, 'error');
            } finally {
                button.disabled = false;
            }
        }

        function createPowerIdempotencyKey() {
            if (root.crypto?.randomUUID) return `lab-manager:${root.crypto.randomUUID()}`;
            return `lab-manager:${Date.now()}:${Math.random().toString(36).slice(2)}`;
        }

        async function load(options = {}) {
            const { forceStatusRefresh = false, ...fetchOptions } = options;
            fetchOptions.cache = 'no-store';
            powerControllerStatusRequestId += 1;
            if (fields.status) {
                fields.status.textContent = 'Loading...';
                fields.status.className = 'pill soft';
            }
            try {
                const response = await fetchImpl('/ops/api/power/controllers', fetchOptions);
                if (response.status === 403) {
                    showOpsWarning();
                    return false;
                }
                if (response.status === 401) {
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power controllers', 'error');
                    return false;
                }
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                powerControllers = Array.isArray(body.controllers) ? body.controllers : [];
                powerControllerStatusLoading = powerControllers.length > 0;
                powerControllerStatusError = false;
                renderList();
                renderOptions();
                renderPolicySteps();
                if (fields.status) {
                    fields.status.textContent = `${powerControllers.length} controller${powerControllers.length === 1 ? '' : 's'}`;
                    fields.status.className = 'pill good';
                }
                if (fields.hint) {
                    fields.hint.textContent = powerControllers.length
                        ? 'Protected outlets require an explicit maintenance mode toggle. Physical activation remains subject to provider hardware validation.'
                        : 'No controller is configured. Add one to the provider-local power catalog before using this panel.';
                }
                if (powerControllers.length) {
                    void loadStatuses({
                        forceRefresh: forceStatusRefresh,
                        skipAuthPrompt: options.skipAuthPrompt,
                    });
                }
                return true;
            } catch (error) {
                logger.warn('Unable to load power controllers', error);
                powerControllers = [];
                powerControllerStatusLoading = false;
                powerControllerStatusError = false;
                renderList();
                renderOptions();
                renderPolicySteps();
                if (fields.status) {
                    fields.status.textContent = 'Unavailable';
                    fields.status.className = 'pill bad';
                }
                if (fields.hint) fields.hint.textContent = 'Power controllers could not be loaded.';
                return false;
            }
        }

        async function loadStatuses(options = {}) {
            const { forceRefresh = false, ...fetchOptions } = options;
            fetchOptions.cache = 'no-store';
            const requestId = ++powerControllerStatusRequestId;
            if (!powerControllers.length) {
                powerControllerStatusLoading = false;
                powerControllerStatusError = false;
                renderList();
                return;
            }
            powerControllerStatusLoading = true;
            powerControllerStatusError = false;
            renderList();
            const query = forceRefresh ? '?refresh=true' : '';
            try {
                const response = await fetchImpl(`/ops/api/power/controllers/status${query}`, fetchOptions);
                if (response.status === 403) {
                    showOpsWarning();
                    throw new Error('Power controller status access denied');
                }
                if (response.status === 401) {
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load power controller status', 'error');
                    throw new Error('Lab Manager session required');
                }
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                if (!Array.isArray(body.controllers)) throw new Error('Power controller status is invalid');
                if (requestId !== powerControllerStatusRequestId) return;
                powerControllers = mergePowerControllerStatuses(powerControllers, body.controllers);
                powerControllerStatusError = false;
                if (!powerControllerEditorDirty && fields.select?.value) loadSelected();
                renderPolicySteps();
            } catch (error) {
                if (requestId !== powerControllerStatusRequestId) return;
                logger.warn('Unable to load power controller status', error);
                powerControllerStatusError = true;
            } finally {
                if (requestId === powerControllerStatusRequestId) {
                    powerControllerStatusLoading = false;
                    renderList();
                }
            }
        }

        function initialize() {
            fields.list?.addEventListener('click', handleActions);
            fields.refresh?.addEventListener('click', () => load({ forceStatusRefresh: true }));
            fields.select?.addEventListener('change', loadSelected);
            fields.driver?.addEventListener('change', updateDriverFields);
            fields.driver?.addEventListener('change', suggestId);
            fields.driver?.addEventListener('change', renderCredentialOptions);
            fields.host?.addEventListener('input', suggestId);
            fields.id?.addEventListener('input', () => {
                powerControllerIdWasSuggested = false;
                powerControllerEditorDirty = true;
            });
            fields.netioHttps?.addEventListener('change', updateNetioPort);
            fields.addOutlet?.addEventListener('click', addOutlet);
            fields.outlets?.addEventListener('change', handleOutletChange);
            fields.outlets?.addEventListener('input', handleOutletChange);
            fields.outlets?.addEventListener('click', handleOutletActions);
            fields.saveButton?.addEventListener('click', save);
            [
                fields.name,
                fields.enabled,
                fields.port,
                fields.credentialRef,
                fields.netioPath,
                fields.netioVerifyTls,
                fields.profile,
                fields.timeoutSeconds,
                fields.retries,
            ].forEach(field => {
                field?.addEventListener('input', () => { powerControllerEditorDirty = true; });
                field?.addEventListener('change', () => { powerControllerEditorDirty = true; });
            });
            updateDriverFields();
        }

        return Object.freeze({
            addOutlet,
            getControllers: () => powerControllers,
            handleOutletChange,
            handleOutletActions,
            setCredentials,
            handleActions,
            initialize,
            load,
            loadSelected,
            loadStatuses,
            populateForm,
            readForm,
            renderCredentialOptions,
            renderList,
            renderOptions,
            resetEditor,
            save,
            suggestId,
            updateDriverFields,
            updateNetioPort,
        });
    }

    root.LabManagerPowerControllers = Object.freeze({ createController });
})(window);
