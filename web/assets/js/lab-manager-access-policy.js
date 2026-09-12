(function (root) {
    'use strict';

    function createController({ document, fetchImpl }) {
        if (!document || typeof fetchImpl !== 'function') {
            throw new Error('LabManagerAccessPolicy requires document and fetchImpl');
        }

        function getBadge() {
            return document.querySelector('#labManagerAccessBadge');
        }

        function clearBadgeClasses(badge) {
            badge.classList.remove('local', 'private', 'external', 'token-required-action');
        }

        async function loadAccessPolicy() {
            const badge = getBadge();
            if (!badge) return;
            try {
                const response = await fetchImpl('/lab-manager/access-policy', {
                    credentials: 'include',
                    skipAuthPrompt: true,
                });
                if (response.status === 401) {
                    badge.textContent = 'Lab Manager session required';
                    clearBadgeClasses(badge);
                    return;
                }
                if (response.status === 403) {
                    badge.textContent = 'Access Policy Blocked';
                    clearBadgeClasses(badge);
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const status = await response.json();
                updateAccessPolicyBadge(status);
            } catch (_error) {
                badge.textContent = 'Access Policy Unavailable';
                clearBadgeClasses(badge);
            }
        }

        function updateAccessPolicyBadge(status) {
            const badge = getBadge();
            if (!badge || !status) return;

            const localOnly = status.dashboardLocalOnly !== false;
            const privateEnabled = status.allowPrivateNetworks === true && status.dashboardAllowPrivate === true;
            const cidrs = typeof status.dashboardAllowedCidrs === 'string'
                ? status.dashboardAllowedCidrs.split(',').map(item => item.trim()).filter(Boolean)
                : [];

            clearBadgeClasses(badge);
            if (!localOnly) {
                badge.textContent = 'External Access Allowed';
                badge.classList.add('external');
            } else if (privateEnabled && cidrs.length > 0) {
                badge.textContent = 'Private CIDR Allowlist';
                badge.title = cidrs.join(', ');
                badge.classList.add('private');
            } else if (privateEnabled) {
                badge.textContent = 'Any Private Network';
                badge.classList.add('private');
            } else {
                badge.textContent = 'Localhost Only';
                badge.classList.add('local');
            }
        }

        return Object.freeze({
            loadAccessPolicy,
            updateAccessPolicyBadge,
        });
    }

    root.LabManagerAccessPolicy = Object.freeze({ createController });
})(window);
