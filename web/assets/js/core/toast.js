(function (root) {
    'use strict';

    function createController({ document, setTimeoutImpl }) {
        function showToast(message, type = 'info') {
            const toast = document.querySelector('#toast');
            toast.textContent = message;
            toast.className = `toast show ${type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
            setTimeoutImpl(() => { toast.className = 'toast'; }, 2500);
        }

        return Object.freeze({ showToast });
    }

    root.LabManagerToast = Object.freeze({ createController });
})(window);
