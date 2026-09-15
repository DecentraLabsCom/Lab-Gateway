(function (root) {
    'use strict';

    function createController() {
        function createPowerPolicyStepDraft(step = {}) {
            const action = String(step.action || 'on').trim().toLowerCase();
            const conditions = step.conditions && typeof step.conditions === 'object' && !Array.isArray(step.conditions)
                ? step.conditions
                : {};
            const readInteger = (value, fallback) => {
                const parsed = Number.parseInt(value, 10);
                return Number.isInteger(parsed) ? parsed : fallback;
            };
            return {
                id: String(step.id || step.stepId || '').trim(),
                phase: String(step.phase || 'pre_start').trim().toLowerCase(),
                controllerId: String(step.controllerId || step.controller_id || '').trim(),
                outlet: String(step.outlet || step.outletKey || step.outlet_key || '').trim(),
                stepLabel: String(step.stepLabel || step.step_label || step.logicalName || step.logical_name || '').trim(),
                action: ['on', 'off', 'cycle'].includes(action) ? action : 'on',
                required: step.required !== false,
                readBackRequired: step.readBackRequired !== false && step.read_back_required !== false,
                offSeconds: readInteger(step.offSeconds ?? step.off_seconds, 10),
                delayBeforeSeconds: readInteger(step.delayBeforeSeconds ?? step.delay_before_seconds, 0),
                delayAfterSeconds: readInteger(step.delayAfterSeconds ?? step.delay_after_seconds, 0),
                timeoutSeconds: readInteger(step.timeoutSeconds ?? step.timeout_seconds, 20),
                retryCount: readInteger(step.retryCount ?? step.retry_count, 0),
                allowProtected: step.allowProtected === true || step.allow_protected === true,
                conditionsText: JSON.stringify(conditions, null, 2),
            };
        }

        function createPowerControllerOutletDraft(outlet = {}) {
            const deviceConfig = outlet.deviceConfig && typeof outlet.deviceConfig === 'object' && !Array.isArray(outlet.deviceConfig)
                ? { ...outlet.deviceConfig }
                : {};
            const deviceConfigFields = Array.isArray(outlet.deviceConfigFields)
                ? outlet.deviceConfigFields.map(field => String(field))
                : [];
            return {
                outlet: String(outlet.outlet || outlet.outletKey || '').trim(),
                displayName: String(outlet.displayName || '').trim(),
                deviceName: String(outlet.deviceName || outlet.name || '').trim(),
                deviceConfig,
                deviceConfigFields,
                deviceConfigWritable: outlet.deviceConfigWritable === true,
                deviceManaged: outlet.deviceManaged === true || deviceConfigFields.length > 0,
                logicalName: String(outlet.logicalName || '').trim(),
                protected: outlet.protected === true,
                critical: outlet.critical === true,
                defaultState: outlet.defaultState === 'on' ? 'on' : 'off',
            };
        }

        function parsePowerPolicyInteger(value, fieldName, maximum) {
            const parsed = Number.parseInt(value, 10);
            if (!Number.isInteger(parsed) || parsed < 0 || parsed > maximum) {
                throw new Error(`${fieldName} must be between 0 and ${maximum}`);
            }
            return parsed;
        }

        return Object.freeze({
            createPowerControllerOutletDraft,
            createPowerPolicyStepDraft,
            parsePowerPolicyInteger,
        });
    }

    root.LabManagerPowerValues = Object.freeze({ createController });
})(window);
