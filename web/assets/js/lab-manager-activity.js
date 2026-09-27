(function (root) {
    'use strict';

    function createController({
        document,
        fetchImpl,
        requestJson = null,
        escapeHtml,
        normalizePagination,
        showToast = () => {},
        logger = root.console || { error() {} },
    }) {
        if (!document || typeof fetchImpl !== 'function' || typeof escapeHtml !== 'function') {
            throw new Error('LabManagerActivity requires document, fetchImpl and escapeHtml');
        }
        if (typeof normalizePagination !== 'function') {
            throw new Error('LabManagerActivity requires normalizePagination');
        }
        if (requestJson !== null && typeof requestJson !== 'function') {
            throw new Error('LabManagerActivity requires requestJson when provided');
        }

        const state = {
            limit: 8,
            offset: 0,
            operations: [],
            pagination: null,
            loading: false,
            loadMoreButton: null,
        };

        function getActivityFeed() {
            return document.querySelector('#activityFeedList');
        }

        async function loadJson(url, options) {
            if (requestJson) return requestJson(url, options);
            const response = await fetchImpl(url, options);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        }

        async function loadActivityFeed(append = false, options = {}) {
            const { notify = false, preserveLoaded = false, ...requestOptions } = options;
            const activityFeed = getActivityFeed();
            if (!activityFeed || state.loading) return;
            const preserveExisting = !append && preserveLoaded && state.operations.length > 0;
            const previousScrollTop = append || preserveExisting
                ? activityFeed.scrollTop
                : null;
            const requestOffset = append ? state.offset : 0;
            const requestLimit = preserveExisting
                ? Math.max(state.limit, state.operations.length)
                : state.limit;
            if (!append && !preserveExisting) {
                state.offset = 0;
                state.operations = [];
                state.pagination = null;
            }
            state.loading = true;
            if (append || preserveExisting) {
                if (state.loadMoreButton) {
                    state.loadMoreButton.disabled = true;
                    state.loadMoreButton.textContent = 'Loading…';
                }
            } else {
                state.loadMoreButton = null;
                activityFeed.innerHTML = '<div class="empty">Loading recent operations...</div>';
            }
            try {
                const params = new URLSearchParams({
                    limit: String(requestLimit),
                    offset: String(requestOffset),
                });
                const body = await loadJson(`/ops/api/operations/recent?${params.toString()}`, {
                    credentials: 'include',
                    ...requestOptions,
                });
                const entries = Array.isArray(body.operations) ? body.operations : [];
                state.operations = append
                    ? state.operations.concat(entries)
                    : entries;
                state.pagination = normalizePagination(
                    body.pagination,
                    requestOffset,
                    entries.length,
                    requestLimit,
                );
                state.offset = state.pagination.nextOffset;
                state.loading = false;
                renderActivityFeed();
                if (previousScrollTop !== null) activityFeed.scrollTop = previousScrollTop;
                if (notify) showToast(append ? 'More activity loaded' : 'Activity loaded', 'success');
            } catch (error) {
                logger.error(error);
                state.loading = false;
                if (append || preserveExisting) {
                    renderActivityFeed();
                    if (previousScrollTop !== null) activityFeed.scrollTop = previousScrollTop;
                } else {
                    activityFeed.innerHTML = `<div class="empty">Unable to load activity: ${escapeHtml(error.message)}</div>`;
                }
                if (notify) showToast(`Activity load failed: ${error.message}`, 'error');
            } finally {
                state.loading = false;
            }
        }

        function renderActivityFeed() {
            const activityFeed = getActivityFeed();
            if (!activityFeed) return;
            state.loadMoreButton = null;
            if (!state.operations.length) {
                activityFeed.innerHTML = '<div class="empty">No recent activity available yet.</div>';
                return;
            }
            activityFeed.innerHTML = '';
            state.operations.forEach((entry) => {
                activityFeed.appendChild(renderActivityFeedItem(entry));
            });
            const paginationElement = renderActivityFeedPagination(state.pagination);
            if (paginationElement) {
                activityFeed.appendChild(paginationElement);
            }
        }

        function renderActivityFeedPagination(pagination) {
            if (!pagination) return null;
            const footer = document.createElement('div');
            footer.className = 'activity-pagination';
            const summary = document.createElement('div');
            summary.className = 'activity-meta';
            const loadedCount = state.operations.length;
            summary.textContent = pagination.total
                ? `Showing 1-${loadedCount} of ${pagination.total}`
                : `Showing ${pagination.returned} entr${pagination.returned === 1 ? 'y' : 'ies'}`;
            footer.appendChild(summary);
            if (pagination.hasMore) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'mini-btn primary';
                button.textContent = state.loading ? 'Loading…' : 'Load more';
                button.disabled = state.loading;
                button.addEventListener('click', () => {
                    if (!state.loading) {
                        loadActivityFeed(true, { notify: true });
                    }
                });
                footer.appendChild(button);
                state.loadMoreButton = button;
            }
            return footer;
        }

        function renderActivityFeedItem(item) {
            const payloadText = item.payload && typeof item.payload === 'object'
                ? JSON.stringify(item.payload)
                : String(item.payload || '');
            const row = document.createElement('div');
            row.className = 'item';
            row.innerHTML = `
            <div class="item-title">${escapeHtml(item.action)} (${escapeHtml(item.status)})</div>
            <div class="item-meta">${escapeHtml(item.host || 'unknown host')} · ${escapeHtml(formatDateTime(item.createdAt) || 'n/a')}</div>
            <div class="item-description">${escapeHtml(item.message || payloadText)}</div>
        `;
            return row;
        }

        function formatDateTime(value) {
            if (!value) return null;
            try {
                const date = new Date(value);
                return date.toLocaleString();
            } catch (_error) {
                return value;
            }
        }

        return Object.freeze({
            loadActivityFeed,
            renderActivityFeed,
        });
    }

    root.LabManagerActivity = Object.freeze({ createController });
})(window);
