(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        applyNotificationConfig,
        setNotificationsLocked,
        setStatus,
        updateNotificationStatusAction,
        showToast,
        getAuthTokenHandler,
        logger = console,
    }) {
        let notificationAccessReady = false;
        let notificationAccessPromise = null;
        let managerTokenRequired = false;

        function hasNotificationAccess() {
            return notificationAccessReady;
        }

        function loadConfig(onSuccess) {
            setStatus('Loading...');
            updateNotificationStatusAction();
            if (notificationAccessPromise) {
                return notificationAccessPromise.then(accessReady => {
                    if (accessReady && typeof onSuccess === 'function') onSuccess();
                    return accessReady;
                });
            }

            const request = fetchImpl('/lab-admin/notifications', {
                credentials: 'include',
                skipAuthPrompt: true,
            })
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    notificationAccessReady = true;
                    managerTokenRequired = false;
                    applyNotificationConfig(data.config || {});
                    setNotificationsLocked(false);
                    setStatus('Loaded');
                    updateNotificationStatusAction();
                    showToast('Configuration loaded', 'success');
                    if (typeof onSuccess === 'function') onSuccess();
                    return true;
                })
                .catch(err => {
                    notificationAccessReady = false;
                    const needsToken = err.message === 'HTTP 401';
                    if (!needsToken) logger.error(err);
                    managerTokenRequired = needsToken;
                    setNotificationsLocked(true);
                    setStatus(needsToken ? 'Lab Manager token required' : 'Error');
                    updateNotificationStatusAction();
                    showToast(
                        needsToken
                            ? 'Lab Manager access is required to load this Gateway’s notifications'
                            : 'Cannot load config (check Lab Manager access)',
                        'error',
                    );
                    return false;
                });

            let pending;
            pending = request.finally(() => {
                if (notificationAccessPromise === pending) notificationAccessPromise = null;
            });
            notificationAccessPromise = pending;
            return pending.then(accessReady => {
                if (accessReady && typeof onSuccess === 'function') onSuccess();
                return accessReady;
            });
        }

        function promptManagerToken(onSuccess) {
            const handler = getAuthTokenHandler();
            if (!handler || typeof handler.showTokenModal !== 'function') {
                showToast('Token prompt unavailable on this page', 'error');
                return;
            }

            let config = null;
            if (typeof handler.getTokenConfigForPath === 'function') {
                config = handler.getTokenConfigForPath('/lab-admin/notifications');
            }
            if (!config) {
                config = {
                    key: 'lab-manager',
                    login: '/lab-manager/login',
                    title: 'Lab Manager token required',
                    description: 'Enter this Gateway’s Lab Manager token.',
                    invalidMessage: 'Invalid Lab Manager token.',
                };
            }

            handler.showTokenModal(config, () => {
                notificationAccessReady = true;
                if (typeof onSuccess === 'function') onSuccess();
            });
        }

        function requestAccess() {
            return loadConfig().then(accessReady => {
                if (!accessReady && managerTokenRequired) {
                    promptManagerToken(() => loadConfig());
                }
                return accessReady;
            });
        }

        function requireAccess(onAuthenticated, onTokenAuthenticated) {
            if (hasNotificationAccess()) {
                if (typeof onAuthenticated === 'function') onAuthenticated();
                return;
            }

            loadConfig().then(accessReady => {
                if (accessReady) {
                    if (typeof onAuthenticated === 'function') onAuthenticated();
                    return;
                }
                if (managerTokenRequired) {
                    promptManagerToken(onTokenAuthenticated || onAuthenticated);
                }
            });
        }

        return Object.freeze({
            hasNotificationAccess,
            loadConfig,
            promptManagerToken,
            requestAccess,
            requireAccess,
        });
    }

    root.LabManagerNotificationsAccess = Object.freeze({ createController });
})(window);
