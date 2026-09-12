(function (root) {
    'use strict';

    function formatDate(value) {
        if (!value) return 'n/a';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString();
    }

    function formatBool(value) {
        if (value === true) return 'yes';
        if (value === false) return 'no';
        return 'n/a';
    }

    function htmlEscape(value) {
        const text = (value ?? '').toString();
        return text.replace(/[&<>"'`]/g, character => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
            '`': '&#96;',
        })[character] || character);
    }

    root.LabManagerFormatters = Object.freeze({ formatDate, formatBool, htmlEscape });
})(window);
