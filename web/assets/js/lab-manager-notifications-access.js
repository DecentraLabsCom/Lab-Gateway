(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        applyNotificationConfig,
        setNotificationsLocked,
        setStatus,
        updateBillingStatusAction,
        showToast,
        getAuthTokenHandler,
        logger = console,
    }) {
        let billingAccessReady = false;
        let billingAccessPromise = null;
        let billingTokenRequired = false;

        function hasBillingAccess() {
            return billingAccessReady;
        }

        function loadConfig(onSuccess) {
            setStatus('Loading...');
            updateBillingStatusAction();
            if (billingAccessPromise) {
                return billingAccessPromise.then(accessReady => {
                    if (accessReady && typeof onSuccess === 'function') onSuccess();
                    return accessReady;
                });
            }

            const request = fetchImpl('/billing/admin/notifications', {
                credentials: 'include',
                skipAuthPrompt: true,
            })
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    billingAccessReady = true;
                    billingTokenRequired = false;
                    applyNotificationConfig(data.config || {});
                    setNotificationsLocked(false);
                    setStatus('Loaded');
                    updateBillingStatusAction();
                    showToast('Configuration loaded', 'success');
                    if (typeof onSuccess === 'function') onSuccess();
                    return true;
                })
                .catch(err => {
                    billingAccessReady = false;
                    const needsToken = err.message === 'HTTP 401';
                    if (!needsToken) logger.error(err);
                    billingTokenRequired = needsToken;
                    setNotificationsLocked(true);
                    setStatus(needsToken ? 'Gateway administrator token required' : 'Error');
                    updateBillingStatusAction();
                    showToast(
                        needsToken
                            ? 'Enter the Gateway administrator token to load notifications'
                            : 'Cannot load config (check administrator access)',
                        'error',
                    );
                    return false;
                });

            let pending;
            pending = request.finally(() => {
                if (billingAccessPromise === pending) billingAccessPromise = null;
            });
            billingAccessPromise = pending;
            return pending.then(accessReady => {
                if (accessReady && typeof onSuccess === 'function') onSuccess();
                return accessReady;
            });
        }

        function promptBillingToken(onSuccess) {
            const handler = getAuthTokenHandler();
            if (!handler || typeof handler.showTokenModal !== 'function') {
                showToast('Token prompt unavailable on this page', 'error');
                return;
            }

            let config = null;
            if (typeof handler.getTokenConfigForPath === 'function') {
                config = handler.getTokenConfigForPath('/billing/admin/notifications');
            }
            if (!config) {
                config = {
                    key: 'billing',
                    login: '/admin/login',
                    header: 'X-Access-Token',
                    cookie: 'access_token',
                    title: 'Gateway administrator token required',
                    description: 'Enter the Gateway administrator token for Wallet & Billing.',
                    invalidMessage: 'Invalid Gateway administrator token.',
                };
            }

            handler.showTokenModal(config, () => {
                billingAccessReady = true;
                if (typeof onSuccess === 'function') onSuccess();
            });
        }

        function requestAccess() {
            return loadConfig().then(accessReady => {
                if (!accessReady && billingTokenRequired) {
                    promptBillingToken(() => loadConfig());
                }
                return accessReady;
            });
        }

        function requireAccess(onAuthenticated, onTokenAuthenticated) {
            if (hasBillingAccess()) {
                if (typeof onAuthenticated === 'function') onAuthenticated();
                return;
            }

            loadConfig().then(accessReady => {
                if (accessReady) {
                    if (typeof onAuthenticated === 'function') onAuthenticated();
                    return;
                }
                if (billingTokenRequired) {
                    promptBillingToken(onTokenAuthenticated || onAuthenticated);
                }
            });
        }

        return Object.freeze({
            hasBillingAccess,
            loadConfig,
            promptBillingToken,
            requestAccess,
            requireAccess,
        });
    }

    root.LabManagerNotificationsAccess = Object.freeze({ createController });
})(window);
