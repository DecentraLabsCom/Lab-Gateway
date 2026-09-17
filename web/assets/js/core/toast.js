(function (root) {
    'use strict';

    let defaultController;

    function createController({ document, setTimeoutImpl, clearTimeoutImpl = () => {} }) {
        let hideTimer;

        function clearHideTimer() {
            if (hideTimer !== undefined) {
                clearTimeoutImpl(hideTimer);
                hideTimer = undefined;
            }
        }

        function clearAccessibilityState(toast) {
            toast.removeAttribute?.('role');
            toast.removeAttribute?.('aria-live');
            toast.removeAttribute?.('aria-busy');
        }

        function showToast(message, type = 'info') {
            const toast = document.querySelector('#toast');
            clearHideTimer();
            toast.textContent = message;
            const isLoading = type === 'loading';
            toast.className = `toast show ${isLoading ? 'loading' : type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
            if (isLoading) {
                toast.setAttribute?.('role', 'status');
                toast.setAttribute?.('aria-live', 'polite');
                toast.setAttribute?.('aria-busy', 'true');
                return;
            }
            clearAccessibilityState(toast);
            hideTimer = setTimeoutImpl(() => {
                toast.className = 'toast';
                hideTimer = undefined;
            }, 2500);
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
