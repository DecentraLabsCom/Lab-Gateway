(function (root) {
    'use strict';

    function normalizePagination(pagination, offset, returned, limitFallback, defaultLimit = 100) {
        const limit = Math.max(1, Number(pagination?.limit) || limitFallback || defaultLimit);
        const total = Number.isFinite(Number(pagination?.total)) ? Number(pagination.total) : offset + returned;
        const nextOffset = Number.isFinite(Number(pagination?.nextOffset)) ? Number(pagination.nextOffset) : offset + returned;
        const hasMore = typeof pagination?.hasMore === 'boolean' ? pagination.hasMore : total > nextOffset;
        const page = Number.isFinite(Number(pagination?.page)) ? Number(pagination.page) : Math.floor(offset / limit) + 1;
        const pageSize = Number.isFinite(Number(pagination?.pageSize)) ? Number(pagination.pageSize) : limit;
        return {
            limit,
            offset,
            returned,
            total,
            nextOffset,
            hasMore,
            page,
            pageSize,
        };
    }

    root.LabManagerPagination = Object.freeze({ normalizePagination });
})(window);
