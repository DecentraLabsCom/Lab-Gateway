(function (root) {
    'use strict';

    function createController({
        dateTimeFormatCtor = root.Intl?.DateTimeFormat,
        dateCtor = root.Date,
        formatDate,
        now = () => Date.now(),
    } = {}) {
        if (typeof dateTimeFormatCtor !== 'function') {
            throw new Error('LabManagerReservationValues requires DateTimeFormat');
        }
        if (typeof dateCtor !== 'function') {
            throw new Error('LabManagerReservationValues requires Date');
        }
        if (typeof formatDate !== 'function') {
            throw new Error('LabManagerReservationValues requires formatDate');
        }
        if (typeof now !== 'function') {
            throw new Error('LabManagerReservationValues requires now');
        }

        function formatReservationDate(epochSeconds) {
            const timestamp = Number(epochSeconds);
            if (!Number.isFinite(timestamp)) return 'Unknown time';
            return new dateTimeFormatCtor(undefined, { dateStyle: 'medium', timeStyle: 'short' })
                .format(new dateCtor(timestamp * 1000));
        }

        function isReservationWindowEnded(reservation) {
            const end = Number(reservation?.end);
            return Number.isFinite(end) && end > 0 && end <= Math.floor(now() / 1000);
        }

        function normalizeReservationStatus(status) {
            const numericStatus = Number(status);
            return Number.isInteger(numericStatus) ? numericStatus : null;
        }

        function cancellationButtonLabel(status, reasonCode) {
            if (status === 0) return 'Decline request';
            if (status === 2 || reasonCode === 8) return 'Report service failure';
            return 'Cancel reservation';
        }

        function shortAddress(value, prefixLength = 6, suffixLength = 4) {
            const text = String(value || '');
            if (text.length <= prefixLength + suffixLength + 3) return text;
            return `${text.slice(0, prefixLength)}…${text.slice(-suffixLength)}`;
        }

        function formatRange(start, end) {
            if (!start && !end) return 'n/a';
            return `${formatDate(start)} → ${formatDate(end)}`;
        }

        return Object.freeze({
            cancellationButtonLabel,
            formatRange,
            formatReservationDate,
            isReservationWindowEnded,
            normalizeReservationStatus,
            shortAddress,
        });
    }

    root.LabManagerReservationValues = Object.freeze({ createController });
})(window);
