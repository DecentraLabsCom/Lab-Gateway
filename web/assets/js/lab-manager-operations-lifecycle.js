(function (root) {
    'use strict';

    function createController({
        hasHostList = false,
        hasReservationList = false,
        refreshSession = async () => false,
        loadManagedLabs = async () => {},
        checkAvailability = async () => false,
        loadHostInventory = async () => {},
        loadActionableReservations = async () => {},
        loadActivityFeed = async () => {},
    } = {}) {
        async function initialize() {
            await refreshSession();
            await loadManagedLabs({ skipAuthPrompt: true });
            checkAvailability();
            if (hasHostList) loadHostInventory({ skipAuthPrompt: true });
            if (hasReservationList) loadActionableReservations({ skipAuthPrompt: true });
            // Let the shared auth handler recover an expired session and retry
            // this request. A valid Lab Manager session does not prompt;
            // suppressing the handler turns an expired session into a
            // misleading visible HTTP 401.
            loadActivityFeed(false);
        }

        return Object.freeze({ initialize });
    }

    root.LabManagerOperationsLifecycle = Object.freeze({ createController });
})(window);
