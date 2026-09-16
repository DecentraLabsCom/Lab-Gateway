(function (root) {
    'use strict';

    function createController({
        timelineInput,
        timelineBtn,
        timelineResult,
        fetchImpl,
        normalizePagination,
        renderTimelineMarkup,
        showToast = () => {},
        logger = console,
        defaultLimit = 100,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerTimeline requires fetchImpl');
        }
        if (typeof normalizePagination !== 'function') {
            throw new Error('LabManagerTimeline requires normalizePagination');
        }
        if (typeof renderTimelineMarkup !== 'function') {
            throw new Error('LabManagerTimeline requires renderTimelineMarkup');
        }

        const timelineState = {
            reservationId: null,
            limit: defaultLimit,
            operations: [],
            base: null,
            pagination: null,
            nextOffset: 0,
            loading: false,
        };

        function setTimelineMessage(message) {
            if (!timelineResult) return;
            timelineResult.classList.add('empty');
            timelineResult.textContent = message;
        }

        function renderTimelineState() {
            if (!timelineResult || !timelineState.base) return;
            const payload = {
                ...timelineState.base,
                operations: [...timelineState.operations],
                pagination: timelineState.pagination,
            };
            renderTimeline(payload);
        }

        function renderTimeline(data) {
            if (!timelineResult) return;
            timelineResult.classList.remove('empty');
            timelineResult.innerHTML = renderTimelineMarkup(data);
            const loadMoreBtn = timelineResult.querySelector('#timelineLoadMoreBtn');
            if (loadMoreBtn) {
                loadMoreBtn.addEventListener('click', () => loadMoreTimeline(loadMoreBtn));
            }
        }

        function resetTimelineState(reservationId) {
            timelineState.reservationId = reservationId;
            timelineState.operations = [];
            timelineState.base = null;
            timelineState.pagination = null;
            timelineState.nextOffset = 0;
            timelineState.limit = defaultLimit;
            timelineState.loading = false;
        }

        async function fetchTimeline() {
            if (!timelineResult || !timelineInput) return;
            const reservationId = (timelineInput.value || '').trim();
            if (!reservationId) {
                const message = 'Provide a reservation id.';
                setTimelineMessage(message);
                showToast(message, 'error');
                timelineInput.focus();
                return;
            }
            resetTimelineState(reservationId);
            await requestTimelinePage(0, false);
        }

        async function requestTimelinePage(offset, append) {
            if (!timelineState.reservationId || timelineState.loading) return;
            timelineState.loading = true;
            if (!append) {
                setTimelineMessage('Loading timeline...');
            }
            try {
                const params = new URLSearchParams({
                    reservationId: timelineState.reservationId,
                    limit: String(timelineState.limit),
                    offset: String(offset),
                });
                const res = await fetchImpl(`/ops/api/reservations/timeline?${params.toString()}`);
                if (res.status === 403) {
                    const msg = 'Access denied: /ops blocked by Lab Manager access policy';
                    if (!append) setTimelineMessage(msg);
                    showToast(msg, 'error');
                    return;
                }
                if (res.status === 401) {
                    const msg = 'Unauthorized: check LAB_MANAGER_TOKEN';
                    if (!append) setTimelineMessage(msg);
                    showToast(msg, 'error');
                    return;
                }
                const body = await res.json();
                if (!res.ok) {
                    const msg = body?.error || `Unable to load timeline (HTTP ${res.status}).`;
                    if (!append) setTimelineMessage(msg);
                    showToast(msg, 'error');
                    return;
                }
                const pageOperations = Array.isArray(body.operations) ? body.operations : [];
                if (!append || !timelineState.base) {
                    timelineState.operations = pageOperations;
                    timelineState.base = body;
                } else {
                    timelineState.operations = timelineState.operations.concat(pageOperations);
                    timelineState.base = { ...timelineState.base, ...body };
                }
                timelineState.pagination = normalizePagination(
                    body.pagination,
                    offset,
                    pageOperations.length,
                    timelineState.limit,
                );
                timelineState.limit = timelineState.pagination.limit;
                timelineState.nextOffset = timelineState.pagination.nextOffset;
                renderTimelineState();
                showToast(append ? 'More timeline operations loaded' : 'Timeline loaded', 'success');
            } catch (err) {
                logger.error(err);
                if (!append) {
                    setTimelineMessage('Timeline request failed.');
                }
                showToast('Timeline request failed', 'error');
            } finally {
                timelineState.loading = false;
            }
        }

        async function loadMoreTimeline(buttonEl) {
            if (!timelineState.pagination?.hasMore || timelineState.loading) {
                return;
            }
            if (buttonEl) {
                buttonEl.disabled = true;
                buttonEl.textContent = 'Loading...';
            }
            await requestTimelinePage(timelineState.nextOffset, true);
        }

        function bind() {
            if (!timelineBtn || !timelineInput || !timelineResult) return false;
            timelineBtn.addEventListener('click', fetchTimeline);
            timelineInput.addEventListener('keydown', event => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    fetchTimeline();
                }
            });
            return true;
        }

        function getState() {
            return {
                ...timelineState,
                operations: [...timelineState.operations],
                base: timelineState.base ? { ...timelineState.base } : null,
                pagination: timelineState.pagination ? { ...timelineState.pagination } : null,
            };
        }

        return Object.freeze({
            bind,
            fetchTimeline,
            loadMoreTimeline,
            resetTimelineState,
            getState,
        });
    }

    root.LabManagerTimeline = Object.freeze({ createController });
})(window);
