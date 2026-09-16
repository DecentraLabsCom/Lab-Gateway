(function (root) {
    'use strict';

    let defaultController;

    function createController({ document, setTimeoutImpl }) {
        function showToast(message, type = 'info') {
            const toast = document.querySelector('#toast');
            toast.textContent = message;
            toast.className = `toast show ${type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
            setTimeoutImpl(() => { toast.className = 'toast'; }, 2500);
        }

        return Object.freeze({ showToast });
    }

    function getDefaultController({ document = root.document, setTimeoutImpl = root.setTimeout } = {}) {
        if (!defaultController) {
            defaultController = createController({ document, setTimeoutImpl });
        }
        return defaultController;
    }

    root.LabManagerToast = Object.freeze({ createController, getDefaultController });
})(window);
