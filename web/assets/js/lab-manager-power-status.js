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
                const statusOutlets = new Map(
                    (Array.isArray(status.outlets) ? status.outlets : [])
                        .filter(outlet => outlet && outlet.outlet !== undefined)
                        .map(outlet => [String(outlet.outlet), outlet]),
                );
                return {
                    ...controller,
                    discovery: status.discovery || {},
                    outlets: (Array.isArray(controller.outlets) ? controller.outlets : []).map(outlet => ({
                        ...outlet,
                        state: statusOutlets.get(String(outlet.outlet))?.state || 'unknown',
                    })),
                };
            });
        }

        return Object.freeze({ mergePowerControllerStatuses });
    }

    root.LabManagerPowerStatus = Object.freeze({ createController });
})(window);
