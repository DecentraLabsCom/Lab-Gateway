(function (root) {
    'use strict';

    function createController({
        hostListEl,
        hostState = {},
        callbacks = {},
    } = {}) {
        const {
            onEditHost = () => {},
            onPoll = () => {},
            onWakeOps = () => {},
            onWinrm = () => {},
            onToggleLocalMode = () => {},
            onCredentials = () => {},
            onTrust = () => {},
            onFmuStation = () => {},
        } = callbacks;

        function handle(event) {
            const button = event.target.closest('button[data-action]');
            if (!button) return;
            const host = button.closest('.host-row')?.dataset.host;
            if (!host) return;
            const action = button.dataset.action;
            if (action === 'edit-host') {
                onEditHost(host);
                return;
            }
            if (action === 'poll') {
                onPoll(host);
                return;
            }
            if (action === 'wake-ops') {
                onWakeOps(host);
                return;
            }
            if (action === 'prepare') {
                onWinrm(host, 'prepare-session', ['--guard-grace=90']);
                return;
            }
            if (action === 'release') {
                onWinrm(host, 'release-session', []);
                return;
            }
            if (action === 'shutdown') {
                onWinrm(host, 'power', ['shutdown', '--delay=60', '--reason=Remote order']);
                return;
            }
            if (action === 'toggle-local-mode') {
                const state = hostState[host] || {};
                const heartbeat = state.heartbeat || {};
                const status = heartbeat.status || heartbeat.station || heartbeat;
                const currentMode = typeof status.localModeEnabled === 'boolean'
                    ? status.localModeEnabled
                    : state.normalized?.localModeEnabled ?? heartbeat.localModeEnabled;
                if (typeof currentMode === 'boolean') onToggleLocalMode(host, !currentMode);
                return;
            }
            if (action === 'set-winrm-credentials') {
                onCredentials(host);
                return;
            }
            if (action === 'manage-winrm-trust') {
                onTrust(host);
                return;
            }
            if (action === 'link-fmu' || action === 'release-fmu') {
                onFmuStation(host, action);
            }
        }

        function bind() {
            if (hostListEl) hostListEl.addEventListener('click', handle);
        }

        return Object.freeze({ bind, handle });
    }

    root.LabManagerHostActionBindings = Object.freeze({ createController });
})(window);
