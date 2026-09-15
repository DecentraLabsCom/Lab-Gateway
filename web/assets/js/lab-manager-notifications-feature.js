(function (root) {
    'use strict';

    function createController({
        documentImpl = root.document,
        fetchImpl,
        showToast = () => {},
        getAuthTokenHandler = () => root.AuthTokenHandler,
        logger = console,
    }) {
        if (!root.LabManagerNotifications) {
            throw new Error('LabManagerNotifications must load before the notifications feature');
        }
        const notificationsController = root.LabManagerNotifications.createController({
            documentImpl,
            fetchImpl,
            showToast,
            getAuthTokenHandler,
            logger,
        });

        return Object.freeze({
            initialize: notificationsController.initialize,
            requestAccess: notificationsController.requestAccess,
        });
    }

    root.LabManagerNotificationsFeature = Object.freeze({ createController });
})(window);
