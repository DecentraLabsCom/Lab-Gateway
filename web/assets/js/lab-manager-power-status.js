(function (root) {
    'use strict';

    function createController() {
        function mergePowerControllerStatuses(controllers, statuses) {
            const statusById = new Map(
                (Array.isArray(statuses) ? statuses : [])
                    .filter(controller => controller && controller.id)
                    .map(controller => [String(controller.id), controller]),
            );
            return (Array.isArray(controllers) ? controllers : []).map(controller => {
                const status = statusById.get(String(controller.id));
                if (!status) return controller;
                const localOutlets = new Map(
                    (Array.isArray(controller.outlets) ? controller.outlets : [])
                        .filter(outlet => outlet && outlet.outlet !== undefined)
                        .map(outlet => [String(outlet.outlet), outlet]),
                );
                const statusOutlets = (Array.isArray(status.outlets) ? status.outlets : [])
                    .filter(outlet => outlet && outlet.outlet !== undefined)
                    .map(outlet => {
                        const local = localOutlets.get(String(outlet.outlet)) || {};
                        return {
                            ...local,
                            ...outlet,
                            state: outlet.state || 'unknown',
                            deviceManaged: true,
                        };
                    });
                return {
                    ...controller,
                    discovery: status.discovery || {},
                    deviceConfiguration: status.deviceConfiguration || controller.deviceConfiguration || {},
                    outlets: Array.isArray(status.outlets)
                        ? statusOutlets
                        : (Array.isArray(controller.outlets) ? controller.outlets : []).map(outlet => ({
                            ...outlet,
                            state: 'unknown',
                        })),
                };
            });
        }

        return Object.freeze({ mergePowerControllerStatuses });
    }

    root.LabManagerPowerStatus = Object.freeze({ createController });
})(window);
