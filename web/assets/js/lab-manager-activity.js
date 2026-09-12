(function (root) {
    'use strict';

    function createController({
        document,
        fetchImpl,
        requestJson = null,
        escapeHtml,
        normalizePagination,
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
            const activityFeed = getActivityFeed();
            if (!activityFeed) return;
            if (!append) {
                state.offset = 0;
                state.operations = [];
                state.pagination = null;
            }
            state.loading = true;
            activityFeed.innerHTML = '<div class="empty">Loading recent operations...</div>';
            try {
                const params = new URLSearchParams({
                    limit: String(state.limit),
                    offset: String(state.offset),
                });
                const body = await loadJson(`/ops/api/operations/recent?${params.toString()}`, {
                    credentials: 'include',
                    ...options,
                });
                const entries = Array.isArray(body.operations) ? body.operations : [];
                state.operations = append
                    ? state.operations.concat(entries)
                    : entries;
                state.pagination = normalizePagination(
                    body.pagination,
                    state.offset,
                    entries.length,
                    state.limit,
                );
                state.offset = state.pagination.nextOffset;
                renderActivityFeed();
            } catch (error) {
                logger.error(error);
                activityFeed.innerHTML = `<div class="empty">Unable to load activity: ${escapeHtml(error.message)}</div>`;
            } finally {
                state.loading = false;
            }
        }

        function renderActivityFeed() {
            const activityFeed = getActivityFeed();
            if (!activityFeed) return;
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
            const start = pagination.returned ? pagination.offset + 1 : pagination.offset;
            const end = pagination.offset + pagination.returned;
            summary.textContent = pagination.total
                ? `Showing ${start}-${end} of ${pagination.total}`
                : `Showing ${pagination.returned} entr${pagination.returned === 1 ? 'y' : 'ies'}`;
            footer.appendChild(summary);
            if (pagination.hasMore) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'mini-btn primary';
                button.textContent = 'Load more';
                button.disabled = state.loading;
                button.addEventListener('click', () => {
                    if (!state.loading) {
                        loadActivityFeed(true);
                    }
                });
                footer.appendChild(button);
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
