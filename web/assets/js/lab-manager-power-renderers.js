(function (root) {
    'use strict';

    function createController({ escapeHtml } = {}) {
        if (typeof escapeHtml !== 'function') {
            throw new Error('LabManagerPowerRenderers requires escapeHtml');
        }

        function renderSwitchField(label, id, fieldAttribute, checked, className = 'field toggle-field power-checkbox-field') {
            return `<div class="${className}">
                <span>${label}</span>
                <label class="switch" for="${id}">
                    <input type="checkbox" id="${id}" ${fieldAttribute}${checked ? ' checked' : ''} aria-label="${label}">
                    <span class="slider"></span>
                </label>
            </div>`;
        }

        function renderPowerPolicyStepsMarkup(stepDrafts, powerControllers) {
            const steps = Array.isArray(stepDrafts) ? stepDrafts : [];
            if (!steps.length) {
                return '<div class="empty">No steps configured. Add a step to control an outlet during a reservation phase.</div>';
            }
            const controllers = Array.isArray(powerControllers) ? powerControllers : [];
            const phases = ['pre_start', 'start', 'post_start', 'pre_end', 'end', 'post_end', 'manual', 'maintenance', 'emergency_stop'];
            const phaseLabels = {
                pre_start: 'Before start',
                start: 'Start',
                post_start: 'After start',
                pre_end: 'Before end',
                end: 'End',
                post_end: 'After end',
                manual: 'Manual',
                maintenance: 'Maintenance',
                emergency_stop: 'Emergency stop',
            };
            const secondsTooltipAttribute = tooltip => ` title="${tooltip}"`;
            return steps.map((step, index) => `
            <div class="power-policy-step" data-step-index="${index}">
                <div class="power-policy-step-header">
                    <div class="power-policy-step-title">
                        <button class="mini-btn power-policy-drag-handle" type="button" draggable="true" data-step-drag-handle aria-label="Drag to reorder Step ${index + 1}" title="Drag to reorder">
                            <i class="fas fa-grip-vertical" aria-hidden="true"></i>
                        </button>
                        <strong>Step ${index + 1}</strong>
                    </div>
                    <button class="mini-btn danger" type="button" data-step-action="remove">Remove</button>
                </div>
                <div class="form-grid power-policy-step-fields">
                    <label class="field">
                        <span>Step label</span>
                        <input type="text" maxlength="160" data-step-field="stepLabel" value="${escapeHtml(step.stepLabel)}" placeholder="Optional label">
                    </label>
                    <label class="field">
                        <span>Phase</span>
                        <select data-step-field="phase">${powerPolicySelectOptions(phases, step.phase, phaseLabels)}</select>
                    </label>
                    <label class="field">
                        <span>Controller</span>
                        <select data-step-field="controllerId">${powerPolicyControllerOptions(step.controllerId, controllers)}</select>
                    </label>
                    <label class="field">
                        <span>Outlet</span>
                        <select data-step-field="outlet">${powerPolicyOutletOptions(step, controllers)}</select>
                    </label>
                    <label class="field">
                        <span>Action</span>
                        <select data-step-field="action">${powerPolicySelectOptions(['on', 'off', 'cycle'], step.action)}</select>
                    </label>
                    ${step.action === 'cycle' ? `
                    <label class="field"${secondsTooltipAttribute('Cycle off time in seconds')}>
                        <span>Cycle off time</span>
                        <input type="number" min="0" max="3600" data-step-field="offSeconds" value="${step.offSeconds}" inputmode="numeric"${secondsTooltipAttribute('Cycle off time in seconds')}>
                    </label>` : ''}
                    <label class="field"${secondsTooltipAttribute('Delay before in seconds')}>
                        <span>Delay before</span>
                        <input type="number" min="0" max="3600" data-step-field="delayBeforeSeconds" value="${step.delayBeforeSeconds}" inputmode="numeric"${secondsTooltipAttribute('Delay before in seconds')}>
                    </label>
                    <label class="field"${secondsTooltipAttribute('Delay after in seconds')}>
                        <span>Delay after</span>
                        <input type="number" min="0" max="3600" data-step-field="delayAfterSeconds" value="${step.delayAfterSeconds}" inputmode="numeric"${secondsTooltipAttribute('Delay after in seconds')}>
                    </label>
                    <label class="field"${secondsTooltipAttribute('Timeout in seconds')}>
                        <span>Timeout</span>
                        <input type="number" min="0" max="300" data-step-field="timeoutSeconds" value="${step.timeoutSeconds}" inputmode="numeric"${secondsTooltipAttribute('Timeout in seconds')}>
                    </label>
                    <label class="field">
                        <span>Retries</span>
                        <input type="number" min="0" max="5" data-step-field="retryCount" value="${step.retryCount}" inputmode="numeric">
                    </label>
                    ${renderSwitchField('Required', `powerPolicyStep${index}Required`, 'data-step-field="required"', step.required)}
                    ${renderSwitchField('Confirm state', `powerPolicyStep${index}ConfirmState`, 'data-step-field="readBackRequired"', step.readBackRequired)}
                    ${renderSwitchField('Allow protected outlet', `powerPolicyStep${index}AllowProtected`, 'data-step-field="allowProtected"', step.allowProtected)}
                </div>
                <label class="field power-policy-conditions">
                    <span>Conditions (advanced JSON, optional)</span>
                    <textarea rows="3" data-step-field="conditions" spellcheck="false">${escapeHtml(step.conditionsText)}</textarea>
                </label>
            </div>
        `).join('');
        }

        function renderPowerControllerCredentialOptionsMarkup(driver, currentValue, powerCredentials) {
            const current = String(currentValue || '').trim();
            const compatibleTypes = driver === 'apc-powernet-snmp'
                ? new Set(['snmpv1', 'snmpv2c', 'snmpv3'])
                : driver === 'netio-json'
                    ? new Set(['netio-http-basic'])
                    : null;
            const credentials = (Array.isArray(powerCredentials) ? powerCredentials : []).filter(credential => {
                const reference = String(credential?.credentialRef || '').trim();
                if (!reference) return false;
                return !compatibleTypes || compatibleTypes.has(String(credential.type || '').trim().toLowerCase());
            });
            const currentIsCompatible = credentials.some(credential =>
                String(credential.credentialRef || '').trim() === current);
            const emptyLabel = driver === 'apc-powernet-snmp'
                ? 'Select SNMP credential'
                : driver === 'netio-json'
                    ? 'No credential (optional)'
                    : 'No credential required';
            const options = [`<option value="">${emptyLabel}</option>`];
            if (current && !currentIsCompatible) {
                options.push(`<option value="${escapeHtml(current)}">${escapeHtml(current)} — unavailable for this driver</option>`);
            }
            credentials.forEach(credential => {
                const reference = String(credential.credentialRef || '').trim();
                const type = String(credential.type || 'unknown').trim();
                options.push(`<option value="${escapeHtml(reference)}">${escapeHtml(reference)} · ${escapeHtml(type)}</option>`);
            });
            return options.join('');
        }

        function renderPowerControllerOutletsMarkup(outletDrafts, options = {}) {
            const outlets = Array.isArray(outletDrafts) ? outletDrafts : [];
            const deviceManaged = options.deviceManaged === true;
            if (!outlets.length) {
                return deviceManaged
                    ? '<div class="empty">No outputs reported by the controller. Refresh its live status.</div>'
                    : '<div class="empty">No outlets configured. Add at least one outlet before saving.</div>';
            }
            return outlets.map((outlet, index) => {
                const outputManagedByDevice = deviceManaged && outlet.deviceManaged === true;
                return `
            <div class="power-controller-outlet-config" data-controller-outlet-index="${index}">
                <div class="power-controller-outlet-config-header">
                    <strong>${deviceManaged ? 'Output' : 'Outlet'} ${index + 1}</strong>
                    ${deviceManaged ? '' : '<button class="mini-btn danger" type="button" data-controller-outlet-action="remove">Remove</button>'}
                </div>
                <div class="form-grid power-controller-outlet-fields">
                    <label class="field">
                        <span>Output ID</span>
                        <input type="text" maxlength="64" data-controller-outlet-field="outlet" value="${escapeHtml(outlet.outlet)}" placeholder="1"${deviceManaged ? ' readonly' : ''}>
                    </label>
                    ${outputManagedByDevice ? renderDeviceConfigurationFields(outlet) : `
                    <label class="field">
                        <span>Name</span>
                        <input type="text" maxlength="160" data-controller-outlet-field="logicalName" value="${escapeHtml(outlet.logicalName)}" placeholder="PLC power">
                    </label>`}
                    <label class="field">
                        <span>Default state</span>
                        <select data-controller-outlet-field="defaultState">
                            <option value="off"${outlet.defaultState === 'off' ? ' selected' : ''}>Off</option>
                            <option value="on"${outlet.defaultState === 'on' ? ' selected' : ''}>On</option>
                        </select>
                    </label>
                    ${renderSwitchField('Protected', `powerControllerOutlet${index}Protected`, 'data-controller-outlet-field="protected"', outlet.protected, 'field toggle-field power-checkbox-field power-controller-outlet-protected-field')}
                </div>
            </div>
        `;
            }).join('');
        }

        function renderDeviceConfigurationFields(outlet) {
            const fields = Array.isArray(outlet.deviceConfigFields) ? outlet.deviceConfigFields : [];
            const config = outlet.deviceConfig && typeof outlet.deviceConfig === 'object' ? outlet.deviceConfig : {};
            const writable = outlet.deviceConfigWritable === true;
            const disabledAttribute = writable ? '' : ' disabled';
            const labels = {
                name: 'Name',
                powerOnDelaySeconds: 'Power-on delay',
                powerOffDelaySeconds: 'Power-off delay',
                rebootDurationSeconds: 'Reboot duration',
            };
            const tooltips = {
                powerOnDelaySeconds: 'Power-on delay in seconds',
                powerOffDelaySeconds: 'Power-off delay in seconds',
                rebootDurationSeconds: 'Reboot duration in seconds',
            };
            return fields.map(field => {
                if (field === 'name') {
                    return `<label class="field">
                        <span>${labels[field]}${writable ? '' : ' (read-only)'}</span>
                        <input type="text" maxlength="20" data-controller-outlet-field="deviceName" value="${escapeHtml(outlet.deviceName)}"${disabledAttribute}>
                    </label>`;
                }
                if (!Object.prototype.hasOwnProperty.call(labels, field)) return '';
                const value = config[field] ?? '';
                const tooltipAttribute = ` title="${tooltips[field]}"`;
                return `<label class="field"${tooltipAttribute}>
                    <span>${labels[field]}${writable ? '' : ' (read-only)'}</span>
                    <input type="number" min="${field === 'rebootDurationSeconds' ? '5' : '0'}" max="${field === 'rebootDurationSeconds' ? '60' : '7200'}" data-controller-device-config-field="${field}" value="${escapeHtml(value)}"${tooltipAttribute}${disabledAttribute}>
                </label>`;
            }).join('');
        }

        function renderPowerControllerRowsMarkup(powerControllers, statusLoading, statusError) {
            return (Array.isArray(powerControllers) ? powerControllers : []).map(controller => {
                const discovery = controller.discovery || {};
                const reachable = discovery.reachable === true;
                const discoveryText = statusLoading
                    ? 'checking'
                    : statusError
                        ? 'status unavailable'
                        : reachable
                            ? 'reachable'
                            : discovery.errorCode ? `unreachable (${discovery.errorCode})` : 'unknown reachability';
                const discoveryClass = statusLoading
                    ? 'soft'
                    : statusError
                        ? 'warn'
                        : reachable ? 'good' : 'warn';
                const safeControllerId = escapeHtml(controller.id);
                const safeName = escapeHtml(controller.name || controller.id);
                const safeDriver = escapeHtml(controller.driver);
                const safeHost = escapeHtml(controller.host || 'local/mock');
                const safeDiscovery = escapeHtml(discoveryText);
                const outlets = Array.isArray(controller.outlets) ? controller.outlets : [];
                return `
                <div class="power-controller-heading">
                    <div>
                        <div class="host-title">${safeName}</div>
                        <div class="host-meta mono">${safeControllerId} · ${safeDriver} · ${safeHost}</div>
                    </div>
                    <span class="pill ${discoveryClass}">${safeDiscovery}</span>
                </div>
                <div class="power-outlet-list">
                    ${outlets.length ? outlets.map(outlet => renderPowerOutletMarkup(controller, outlet)).join('') : '<div class="empty">No outlets configured.</div>'}
                </div>
            `;
            });
        }

        function powerPolicyControllerOptions(selectedId, powerControllers) {
            const options = (Array.isArray(powerControllers) ? powerControllers : []).map(controller => {
                const controllerId = String(controller.id || '').trim();
                const label = controller.name || controllerId;
                return `<option value="${escapeHtml(controllerId)}"${controllerId === selectedId ? ' selected' : ''}>${escapeHtml(label)}</option>`;
            }).join('');
            return `<option value="">Select controller</option>${options}`;
        }

        function powerPolicyOutletOptions(step, powerControllers) {
            const controller = (Array.isArray(powerControllers) ? powerControllers : [])
                .find(item => String(item.id || '') === String(step.controllerId || ''));
            const outlets = Array.isArray(controller?.outlets) ? controller.outlets : [];
            const options = outlets.map(outlet => {
                const outletId = String(outlet.outlet || '').trim();
                const label = outlet.deviceName || outlet.logicalName || outletId;
                return `<option value="${escapeHtml(outletId)}"${outletId === step.outlet ? ' selected' : ''}>${escapeHtml(label)} (${escapeHtml(outletId)})</option>`;
            }).join('');
            return `<option value="">${outlets.length ? 'Select outlet' : 'No outlets available'}</option>${options}`;
        }

        function powerPolicySelectOptions(values, selected, labels = {}) {
            return values.map(value => `<option value="${value}"${value === selected ? ' selected' : ''}>${labels[value] || value}</option>`).join('');
        }

        function renderPowerOutletMarkup(controller, outlet) {
            const protectedOutlet = outlet.protected === true;
            const state = String(outlet.state || 'unknown').toLowerCase();
            const stateClass = state === 'on' ? 'good' : state === 'off' ? 'soft' : 'warn';
            const label = outlet.deviceName || outlet.logicalName || outlet.outlet;
            return `
            <div class="power-outlet-row">
                <div>
                    <div class="item-title">${escapeHtml(label)}</div>
                    <div class="host-meta">Outlet ${escapeHtml(outlet.outlet)}${protectedOutlet ? ' · protected' : ''}</div>
                </div>
                <div class="power-outlet-actions">
                    <span class="pill ${stateClass}">${escapeHtml(state)}</span>
                    <button class="mini-btn" data-power-action="on" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">On</button>
                    <button class="mini-btn" data-power-action="off" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">Off</button>
                    <button class="mini-btn primary" data-power-action="cycle" data-controller-id="${escapeHtml(controller.id)}" data-outlet-id="${escapeHtml(outlet.outlet)}" data-protected="${protectedOutlet}">Cycle</button>
                </div>
            </div>
        `;
        }

        return Object.freeze({
            renderPowerControllerCredentialOptionsMarkup,
            renderPowerControllerOutletsMarkup,
            renderPowerControllerRowsMarkup,
            renderPowerPolicyStepsMarkup,
        });
    }

    root.LabManagerPowerRenderers = Object.freeze({ createController });
})(window);
