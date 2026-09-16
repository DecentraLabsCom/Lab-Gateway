(function (root) {
    'use strict';

    function createController({
        listEl,
        statusEl,
        fetchImpl,
        renderMarkup,
        escapeHtml,
        normalizeReservationStatus,
        cancellationButtonLabel,
        showToast = () => {},
        confirmImpl = message => root.confirm(message),
        createIdempotencyKey = () => {
            if (root.crypto && typeof root.crypto.randomUUID === 'function') {
                return `lab-manager-${root.crypto.randomUUID()}`;
            }
            return `lab-manager-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        },
        logger = console,
        pageSize = 100,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerActionableReservations requires fetchImpl');
        }
        if (typeof renderMarkup !== 'function') {
            throw new Error('LabManagerActionableReservations requires renderMarkup');
        }
        if (typeof escapeHtml !== 'function') {
            throw new Error('LabManagerActionableReservations requires escapeHtml');
        }
        if (typeof normalizeReservationStatus !== 'function') {
            throw new Error('LabManagerActionableReservations requires normalizeReservationStatus');
        }
        if (typeof cancellationButtonLabel !== 'function') {
            throw new Error('LabManagerActionableReservations requires cancellationButtonLabel');
        }

        const state = {
            reservations: [],
            offset: 0,
            nextOffset: 0,
            cursor: null,
            total: null,
            totalKnown: false,
            hasMore: false,
            loading: false,
        };

        function renderMessage(message) {
            if (listEl) {
                listEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
            }
        }

        function setStatus(message, type) {
            if (!statusEl) return;
            statusEl.textContent = message;
            statusEl.className = `pill ${type || 'soft'}`;
        }

        function render() {
            if (!listEl) return;
            if (!state.reservations.length) {
                renderMessage('No actionable reservations for your labs.');
                return;
            }
            listEl.innerHTML = renderMarkup(state.reservations, state.hasMore);
        }

        async function load({ append = false, skipAuthPrompt = false, notify = false } = {}) {
            if (!listEl || state.loading) return;
            if (!append) {
                state.reservations = [];
                state.offset = 0;
                state.nextOffset = 0;
                state.cursor = null;
                state.total = null;
                state.totalKnown = false;
                state.hasMore = false;
            }
            state.loading = true;
            setStatus(append ? 'Loading more...' : 'Loading...', 'soft');
            try {
                const params = new URLSearchParams({
                    limit: String(pageSize),
                    offset: String(state.nextOffset),
                });
                if (state.cursor) {
                    params.set('cursor', state.cursor);
                }
                const res = await fetchImpl(`/lab-admin/reservations/actionable?${params.toString()}`, {
                    credentials: 'include',
                    ...(skipAuthPrompt ? { skipAuthPrompt: true } : {}),
                });
                if (res.status === 401) {
                    renderMessage('Unauthorized: check LAB_MANAGER_TOKEN.');
                    setStatus('Unauthorized', 'bad');
                    if (notify) showToast('Unauthorized: check LAB_MANAGER_TOKEN.', 'error');
                    return;
                }
                if (res.status === 403) {
                    renderMessage('Access denied: provider reservation administration is not available.');
                    setStatus('Access denied', 'bad');
                    if (notify) showToast('Access denied: provider reservation administration is not available.', 'error');
                    return;
                }
                const body = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(body.error || `Unable to load reservations (HTTP ${res.status}).`);
                }
                const page = Array.isArray(body.reservations) ? body.reservations : [];
                const pagination = body.pagination || {};
                const returned = Number.isFinite(Number(pagination.returned))
                    ? Number(pagination.returned)
                    : page.length;
                const nextOffset = Number.isFinite(Number(pagination.nextOffset))
                    ? Number(pagination.nextOffset)
                    : Number.isFinite(Number(body.nextOffset))
                        ? Number(body.nextOffset)
                        : state.nextOffset + returned;
                state.reservations = append
                    ? state.reservations.concat(page)
                    : page;
                state.offset = Number.isFinite(Number(pagination.offset))
                    ? Number(pagination.offset)
                    : Number.isFinite(Number(body.offset))
                        ? Number(body.offset)
                        : state.offset;
                state.nextOffset = nextOffset;
                state.cursor = typeof pagination.nextCursor === 'string'
                    ? pagination.nextCursor
                    : typeof body.nextCursor === 'string'
                        ? body.nextCursor
                        : null;
                state.totalKnown = Number.isFinite(Number(pagination.total))
                    || Number.isFinite(Number(body.totalCount));
                state.total = state.totalKnown
                    ? Number.isFinite(Number(pagination.total))
                        ? Number(pagination.total)
                        : Number(body.totalCount)
                    : null;
                state.hasMore = typeof pagination.hasMore === 'boolean'
                    ? pagination.hasMore
                    : typeof body.hasMore === 'boolean'
                        ? body.hasMore
                        : Boolean(body.truncated);
                render();
                const loadedCount = state.reservations.length;
                const totalCount = state.totalKnown ? state.total : loadedCount;
                const status = state.hasMore
                    ? state.totalKnown
                        ? `${loadedCount} of ${totalCount} actionable`
                        : `${loadedCount}+ actionable`
                    : `${totalCount} actionable`;
                setStatus(status, 'soft');
                if (notify) showToast(append ? 'More reservations loaded' : 'Reservations loaded', 'success');
            } catch (err) {
                logger.error(err);
                if (!append) renderMessage('Unable to load actionable reservations.');
                setStatus('Unavailable', 'bad');
                if (notify) showToast(`Reservations load failed: ${err.message}`, 'error');
            } finally {
                state.loading = false;
            }
        }

        function handleReasonChange(event) {
            const reasonEl = event.target.closest('[data-reservation-reason]');
            if (!reasonEl || !listEl.contains(reasonEl)) return;
            const row = reasonEl.closest('.reservation-item');
            const button = row?.querySelector('[data-action="cancel-reservation"]');
            if (!button) return;
            const reservationStatus = normalizeReservationStatus(row.dataset.reservationStatus);
            button.textContent = cancellationButtonLabel(reservationStatus, Number(reasonEl.value));
        }

        async function handleActions(event) {
            const loadMoreButton = event.target.closest('[data-action="load-more-actionable"]');
            if (loadMoreButton && listEl.contains(loadMoreButton)) {
                await load({ append: true, notify: true });
                return;
            }
            const button = event.target.closest('[data-action="cancel-reservation"]');
            if (!button || !listEl.contains(button)) return;
            const row = button.closest('.reservation-item');
            const key = row?.dataset.reservationKey;
            const reservationStatus = normalizeReservationStatus(row?.dataset.reservationStatus);
            const reasonEl = row?.querySelector('[data-reservation-reason]');
            const reasonCode = Number(reasonEl?.value);
            if (!key || !Number.isInteger(reasonCode)) return;
            const confirmationMessage = reservationStatus === 2 || reasonCode === 8
                ? reservationStatus === 2
                    ? 'Report provider service failure for this access-authorized reservation? The full price returns as service credits.'
                    : 'Report provider service failure for this confirmed reservation? The full price returns as service credits.'
                : 'Cancel this upcoming reservation? A confirmed reservation returns its full price as service credits.';
            if (!confirmImpl(confirmationMessage)) return;

            button.disabled = true;
            if (reasonEl) reasonEl.disabled = true;
            try {
                const res = await fetchImpl(`/lab-admin/reservations/${encodeURIComponent(key)}/cancel`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'Idempotency-Key': createIdempotencyKey(),
                    },
                    body: JSON.stringify({ reasonCode }),
                });
                const body = await res.json().catch(() => ({}));
                if (res.status === 401) throw new Error('Unauthorized: check LAB_MANAGER_TOKEN.');
                if (res.status === 403) throw new Error('Access denied: provider reservation administration is not available.');
                if (!res.ok) throw new Error(body.error || `Cancellation failed (HTTP ${res.status}).`);
                showToast(
                    reasonCode === 8
                        ? 'Provider service-failure report submitted'
                        : 'Reservation cancellation submitted',
                    'success',
                );
                await load();
            } catch (err) {
                logger.error(err);
                showToast(err.message || 'Reservation cancellation failed', 'error');
                button.disabled = false;
                if (reasonEl) reasonEl.disabled = false;
            }
        }

        function bind() {
            if (!listEl) return false;
            listEl.addEventListener('click', handleActions);
            listEl.addEventListener('change', handleReasonChange);
            return true;
        }

        function getState() {
            return {
                ...state,
                reservations: [...state.reservations],
            };
        }

        return Object.freeze({
            bind,
            getState,
            handleActions,
            handleReasonChange,
            load,
        });
    }

    root.LabManagerActionableReservations = Object.freeze({ createController });
})(window);
