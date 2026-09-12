(function (global) {
    function renderLabActionIcon(action) {
        const attributes = 'class="lab-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"';
        if (action === 'edit') {
            return `<svg ${attributes}><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`;
        }
        if (action === 'list') {
            return `<svg ${attributes}><path d="M2.1 12s3.6-6 9.9-6 9.9 6 9.9 6-3.6 6-9.9 6-9.9-6-9.9-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>`;
        }
        if (action === 'unlist') {
            return `<svg ${attributes}><path d="M2.1 12s3.6-6 9.9-6 9.9 6 9.9 6-3.6 6-9.9 6-9.9-6-9.9-6Z"/><circle cx="12" cy="12" r="2.5"/><path d="m3 3 18 18"/></svg>`;
        }
        return `<svg ${attributes}><path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/></svg>`;
    }

    function renderModelVariables({ modelVariables = [], escapeHtml } = {}) {
        const variables = Array.isArray(modelVariables) ? modelVariables : [];
        return {
            hidden: variables.length === 0,
            html: variables.map(variable => `
            <tr>
                <td>${escapeHtml(variable.name || '')}</td>
                <td>${escapeHtml(variable.causality || '')}</td>
                <td>${escapeHtml(variable.type || '')}</td>
                <td>${escapeHtml(variable.unit || '')}</td>
                <td>${escapeHtml(variable.start ?? '')}</td>
            </tr>
        `).join(''),
        };
    }

    global.LabPublisherRenderers = Object.freeze({
        renderLabActionIcon,
        renderModelVariables,
    });
}(window));