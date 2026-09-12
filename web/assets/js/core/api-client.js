(function (root) {
    'use strict';

    function createClient({ fetchImpl } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerApiClient requires fetchImpl');
        }

        async function request(url, options) {
            return fetchImpl(url, options);
        }

        async function requestJson(url, options) {
            const response = await request(url, options);
            if (!response.ok) {
                const error = new Error(`HTTP ${response.status}`);
                error.status = response.status;
                throw error;
            }
            return response.json();
        }

        return Object.freeze({ request, requestJson });
    }

    root.LabManagerApiClient = Object.freeze({ createClient });
})(window);
