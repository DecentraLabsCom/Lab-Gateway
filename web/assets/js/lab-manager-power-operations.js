(function (root) {
    'use strict';

    function createController() {
        function buildPowerCommandPayload(action, options = {}) {
            const protectedOutlet = options.protectedOutlet === true;
            const payload = {
                command: action === 'cycle' ? 'cycle' : 'set_state',
                state: action === 'cycle' ? undefined : action,
                actor: 'lab-manager',
                reason: String(options.reason || '').trim() || 'Lab Manager manual power test',
                idempotencyKey: options.idempotencyKey,
                offSeconds: action === 'cycle' ? options.offSeconds : undefined,
                allowProtected: protectedOutlet,
                maintenance: protectedOutlet && options.maintenance === true,
            };
            Object.keys(payload).forEach(key => payload[key] === undefined && delete payload[key]);
            return payload;
        }

        return Object.freeze({ buildPowerCommandPayload });
    }

    root.LabManagerPowerOperations = Object.freeze({ createController });
})(window);
