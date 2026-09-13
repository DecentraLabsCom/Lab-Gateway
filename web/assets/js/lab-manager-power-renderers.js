(function (root) {
    'use strict';

    function createController({ escapeHtml } = {}) {
        if (typeof escapeHtml !== 'function') {
            throw new Error('LabManagerPowerRenderers requires escapeHtml');
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
            return steps.map((step, index) => `
            <div class="power-policy-step" data-step-index="${index}">
                <div class="power-policy-step-header">
                    <strong>Step ${index + 1}</strong>
                    <button class="mini-btn danger" type="button" data-step-action="remove">Remove</button>
                </div>
                <div class="form-grid power-policy-step-fields">
                    <label class="field">
                        <span>Phase</span>
                        <select data-step-field="phase">${powerPolicySelectOptions(phases, step.phase, phaseLabels)}</select>
                    </label>
                    <label class="field">
                        <span>Sequence</span>
                        <input type="number" min="0" max="1000000" data-step-field="sequence" value="${step.sequence}" inputmode="numeric">
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
                    <label class="field">
                        <span>Desired state</span>
                        <select data-step-field="desiredState">${powerPolicySelectOptions(['', 'on', 'off', 'unknown'], step.desiredState, { '': 'Use action default' })}</select>
                    </label>
                    <label class="field">
                        <span>Logical name</span>
                        <input type="text" maxlength="160" data-step-field="logicalName" value="${escapeHtml(step.logicalName)}" placeholder="Optional label">
                    </label>
                    <label class="field">
                        <span>Cycle off time (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="offSeconds" value="${step.offSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Delay before (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="delayBeforeSeconds" value="${step.delayBeforeSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Delay after (seconds)</span>
                        <input type="number" min="0" max="3600" data-step-field="delayAfterSeconds" value="${step.delayAfterSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Timeout (seconds)</span>
                        <input type="number" min="0" max="300" data-step-field="timeoutSeconds" value="${step.timeoutSeconds}" inputmode="numeric">
                    </label>
                    <label class="field">
                        <span>Retries</span>
                        <input type="number" min="0" max="5" data-step-field="retryCount" value="${step.retryCount}" inputmode="numeric">
                    </label>
                </div>
                <div class="power-policy-step-options">
                    <label class="check-field"><input type="checkbox" data-step-field="required"${step.required ? ' checked' : ''}> Required</label>
                    <label class="check-field"><input type="checkbox" data-step-field="readBackRequired"${step.readBackRequired ? ' checked' : ''}> Read back state</label>
                    <label class="check-field"><input type="checkbox" data-step-field="allowProtected"${step.allowProtected ? ' checked' : ''}> Allow protected outlet</label>
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

        function renderPowerControllerOutletsMarkup(outletDrafts) {
            const outlets = Array.isArray(outletDrafts) ? outletDrafts : [];
            if (!outlets.length) {
                return '<div class="empty">No outlets configured. Add at least one outlet before saving.</div>';
            }
            return outlets.map((outlet, index) => `
            <div class="power-controller-outlet-config" data-controller-outlet-index="${index}">
                <div class="power-controller-outlet-config-header">
                    <strong>Outlet ${index + 1}</strong>
                    <button class="mini-btn danger" type="button" data-controller-outlet-action="remove">Remove</button>
                </div>
                <div class="form-grid power-controller-outlet-fields">
                    <label class="field">
                        <span>Outlet ID</span>
                        <input type="text" maxlength="64" data-controller-outlet-field="outlet" value="${escapeHtml(outlet.outlet)}" placeholder="1">
                    </label>
                    <label class="field">
                        <span>Display name</span>
                        <input type="text" maxlength="160" data-controller-outlet-field="displayName" value="${escapeHtml(outlet.displayName)}" placeholder="PLC power">
                    </label>
                    <label class="field">
                        <span>Logical name</span>
                        <input type="text" maxlength="160" data-controller-outlet-field="logicalName" value="${escapeHtml(outlet.logicalName)}" placeholder="plc">
                    </label>
                    <label class="field">
                        <span>Default state</span>
                        <select data-controller-outlet-field="defaultState">
                            <option value="off"${outlet.defaultState === 'off' ? ' selected' : ''}>Off</option>
                            <option value="on"${outlet.defaultState === 'on' ? ' selected' : ''}>On</option>
                        </select>
                    </label>
                </div>
                <div class="power-controller-outlet-options">
                    <label class="check-field"><input type="checkbox" data-controller-outlet-field="protected"${outlet.protected ? ' checked' : ''}> Protected</label>
                    <label class="check-field"><input type="checkbox" data-controller-outlet-field="critical"${outlet.critical ? ' checked' : ''}> Critical</label>
                </div>
            </div>
        `).join('');
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
                const label = outlet.displayName || outlet.logicalName || outletId;
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
            const label = outlet.displayName || outlet.logicalName || outlet.outlet;
            return `
            <div class="power-outlet-row">
                <div>
                    <div class="item-title">${escapeHtml(label)}</div>
                    <div class="host-meta">Outlet ${escapeHtml(outlet.outlet)}${protectedOutlet ? ' · protected' : ''}${outlet.critical ? ' · critical' : ''}</div>
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
