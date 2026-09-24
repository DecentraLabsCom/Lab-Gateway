(function (root) {
    'use strict';

    function createController({
        hostListEl,
        candidateListEl,
        getHostNames = () => [],
        hostState = {},
        hostMetadata = {},
        candidateState = {},
        hostRenderersController,
        documentImpl = root.document,
        windowImpl = root,
        callbacks = {},
    } = {}) {
        if (!hostRenderersController
            || typeof hostRenderersController.buildHostRow !== 'function'
            || typeof hostRenderersController.buildGuacamoleCandidateRow !== 'function') {
            throw new Error('LabManagerHostView requires hostRenderersController');
        }
        if (!documentImpl || !windowImpl) {
            throw new Error('LabManagerHostView requires documentImpl and windowImpl');
        }

        const {
            onConfigureCandidate = () => {},
            onProbeCandidate = async () => {},
        } = callbacks;
        const popoverClosers = new Set();
        let rawCandidates = [];
        let stationCandidates = [];

        function normalizeMatchValue(value) {
            return (value || '').toString().trim().toLowerCase();
        }

        function closeAllPopovers() {
            Array.from(popoverClosers).forEach(closePopover => closePopover());
        }

        function setupFixedPopover(row, triggerSelector, popoverSelector) {
            const trigger = row.querySelector?.(triggerSelector);
            const popover = row.querySelector?.(popoverSelector);
            if (!trigger || !popover || !documentImpl.body) return;

            let hideTimer = null;
            let isShown = false;

            function clearHideTimer() {
                if (hideTimer === null) return;
                windowImpl.clearTimeout(hideTimer);
                hideTimer = null;
            }

            function positionPopover() {
                if (!isShown) return;

                const triggerRect = trigger.getBoundingClientRect();
                const viewportWidth = windowImpl.innerWidth || documentImpl.documentElement.clientWidth;
                const viewportHeight = windowImpl.innerHeight || documentImpl.documentElement.clientHeight;
                const viewportMargin = 12;
                const gap = 8;
                const popoverWidth = popover.offsetWidth;
                const popoverHeight = popover.offsetHeight;
                let left = triggerRect.left + (triggerRect.width - popoverWidth) / 2;
                let top = triggerRect.bottom + gap;

                if (
                    top + popoverHeight > viewportHeight - viewportMargin
                    && triggerRect.top - popoverHeight - gap >= viewportMargin
                ) {
                    top = triggerRect.top - popoverHeight - gap;
                }
                left = Math.min(
                    Math.max(viewportMargin, left),
                    Math.max(viewportMargin, viewportWidth - popoverWidth - viewportMargin),
                );
                top = Math.min(
                    Math.max(viewportMargin, top),
                    Math.max(viewportMargin, viewportHeight - popoverHeight - viewportMargin),
                );
                popover.style.left = Math.round(left) + 'px';
                popover.style.top = Math.round(top) + 'px';
            }

            function closePopover() {
                clearHideTimer();
                isShown = false;
                popover.classList.remove('is-visible');
                popover.style.left = '';
                popover.style.top = '';
                if (popover.parentElement === documentImpl.body) popover.remove();
                windowImpl.removeEventListener('resize', positionPopover);
                windowImpl.removeEventListener('scroll', positionPopover, true);
                popoverClosers.delete(closePopover);
            }

            function showPopover() {
                clearHideTimer();
                if (popover.parentElement !== documentImpl.body) documentImpl.body.appendChild(popover);
                isShown = true;
                popoverClosers.add(closePopover);
                popover.classList.add('is-visible');
                positionPopover();
                windowImpl.addEventListener('resize', positionPopover);
                windowImpl.addEventListener('scroll', positionPopover, true);
            }

            function scheduleClosePopover() {
                clearHideTimer();
                hideTimer = windowImpl.setTimeout(() => {
                    const triggerHovered = trigger.matches?.(':hover');
                    const popoverHovered = popover.matches?.(':hover');
                    const triggerFocused = documentImpl.activeElement === trigger;
                    if (triggerHovered || popoverHovered || triggerFocused) return;
                    closePopover();
                }, 120);
            }

            trigger.addEventListener('mouseenter', showPopover);
            trigger.addEventListener('mouseleave', scheduleClosePopover);
            trigger.addEventListener('focusin', showPopover);
            trigger.addEventListener('focusout', scheduleClosePopover);
            trigger.addEventListener('keydown', event => {
                if (event.key === 'Escape') closePopover();
            });
            popover.addEventListener('mouseenter', showPopover);
            popover.addEventListener('mouseleave', scheduleClosePopover);
        }

        function closeAllGuacamoleMatchPopovers() {
            closeAllPopovers();
        }

        function setupGuacamoleMatchPopover(row) {
            setupFixedPopover(row, '.guacamole-match-trigger', '.guacamole-match-popover');
        }

        function setupReadinessTooltip(row) {
            setupFixedPopover(row, '.ready-indicator', '.ready-indicator-tooltip');
        }

        function buildHostRow(host) {
            const row = hostRenderersController.buildHostRow(
                host,
                hostState[host] || {},
                hostMetadata[host] || {},
            );
            setupGuacamoleMatchPopover(row);
            setupReadinessTooltip(row);
            return row;
        }

        function renderHosts() {
            if (!hostListEl) return;
            closeAllGuacamoleMatchPopovers();
            hostListEl.innerHTML = '';
            const hostNames = getHostNames();
            if (!hostNames.length) {
                hostListEl.innerHTML = '<div class="empty">No ops hosts loaded. Configure ops-worker/hosts.json.</div>';
                return;
            }
            hostNames.forEach(host => {
                hostListEl.appendChild(buildHostRow(host));
            });
        }

        function renderCandidates(candidates) {
            if (Array.isArray(candidates)) stationCandidates = candidates;
            if (!candidateListEl) return;
            candidateListEl.innerHTML = '';
            if (!stationCandidates.length) {
                candidateListEl.innerHTML = '<div class="empty">All Lab Station candidates are configured or no connections are available.</div>';
                return;
            }
            stationCandidates.forEach(station => {
                candidateListEl.appendChild(hostRenderersController.buildGuacamoleCandidateRow(
                    station,
                    candidateState,
                ));
            });
        }

        async function handleCandidateActions(event) {
            const button = event.target.closest('button[data-action]');
            if (!button) return;
            const row = button.closest('.host-row');
            const stationKey = row?.dataset.stationKey;
            if (!stationKey) return;
            if (button.dataset.action === 'configure-candidate') {
                onConfigureCandidate(stationKey);
                return;
            }
            if (button.dataset.action !== 'probe-candidate') return;
            const station = findStationCandidate(stationKey);
            if (!station) return;
            await onProbeCandidate(stationKey, station, button);
        }

        function stationCandidateKey(candidate) {
            const address = normalizeMatchValue(candidate?.hostname);
            return address ? `host:${address}` : `connection:${String(candidate?.id ?? '')}`;
        }

        function groupCandidates(candidates) {
            const groups = new Map();
            (Array.isArray(candidates) ? candidates : []).forEach(candidate => {
                const key = stationCandidateKey(candidate);
                if (!key || key.endsWith(':')) return;
                let station = groups.get(key);
                if (!station) {
                    station = {
                        key,
                        address: candidate?.hostname || '',
                        nameCandidates: [],
                        connections: [],
                    };
                    groups.set(key, station);
                }
                station.connections.push(candidate);
                const name = String(candidate?.name || '').trim();
                if (name && !station.nameCandidates.includes(name)) {
                    station.nameCandidates.push(name);
                }
            });
            return Array.from(groups.values());
        }

        function findStationCandidate(stationKey) {
            return stationCandidates.find(station => station.key === stationKey) || null;
        }

        function rememberCandidate(candidate) {
            const key = stationCandidateKey(candidate);
            if (!key || key.endsWith(':')) return;
            candidateState[key] = {
                ...(candidateState[key] || {}),
                candidate: candidateState[key]?.candidate || candidate,
                connectionId: candidateState[key]?.connectionId || candidate?.id,
            };
        }

        function setCandidates(candidates) {
            rawCandidates = Array.isArray(candidates) ? candidates : [];
        }

        function bind() {
            if (candidateListEl) candidateListEl.addEventListener('click', handleCandidateActions);
        }

        return Object.freeze({
            bind,
            closeAllGuacamoleMatchPopovers,
            findStationCandidate,
            groupCandidates,
            handleCandidateActions,
            rememberCandidate,
            renderCandidates,
            renderHosts,
            setCandidates,
            stationCandidateKey,
            getState: () => ({ rawCandidates, stationCandidates }),
        });
    }

    root.LabManagerHostView = Object.freeze({ createController });
})(window);
