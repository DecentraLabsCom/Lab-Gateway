(function (root) {
    'use strict';

    function createTabActivationState() {
        const initializedTabs = new Set();

        function claimTab(tabName) {
            if (!tabName || initializedTabs.has(tabName)) return false;
            initializedTabs.add(tabName);
            return true;
        }

        function isTabInitialized(tabName) {
            return initializedTabs.has(tabName);
        }

        return Object.freeze({ claimTab, isTabInitialized });
    }

    root.LabManagerState = Object.freeze({ createTabActivationState });
})(window);
