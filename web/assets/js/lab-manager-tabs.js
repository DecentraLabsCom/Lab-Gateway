document.addEventListener('DOMContentLoaded', () => {
    const DEFAULT_TAB = 'laboratories';
    const main = document.querySelector('.lm-main');
    const tabList = document.querySelector('[role="tablist"]');
    const status = document.querySelector('#lmTabStatus');
    const tabs = Array.from(document.querySelectorAll('[data-lm-tab]'));
    const sections = Array.from(document.querySelectorAll('[data-lm-tab-section]'));
    const panels = new Map();
    const initializedTabs = new Set();
    let activeTab = null;

    if (!main || !tabList || tabs.length === 0) return;

    tabs.forEach(tab => {
        const tabName = tab.dataset.lmTab;
        const panelId = `lm-panel-${tabName}`;
        const panel = document.getElementById(panelId) || document.createElement('div');
        panel.id = panelId;
        panel.classList.add('lm-tab-panel');
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', tab.id);
        panel.hidden = true;

        if (!panel.parentElement) main.appendChild(panel);

        sections
            .filter(section => section.dataset.lmTabSection === tabName)
            .sort((left, right) => Number(left.dataset.lmOrder || 0) - Number(right.dataset.lmOrder || 0))
            .forEach(section => panel.appendChild(section));

        panels.set(tabName, panel);
        main.appendChild(panel);
    });
    document.body.classList.add('lm-tabs-ready');

    function getTab(name) {
        return tabs.find(tab => tab.dataset.lmTab === name) || null;
    }

    function tabFromHash() {
        const candidate = window.location.hash.replace(/^#/, '').trim();
        return getTab(candidate) ? candidate : DEFAULT_TAB;
    }

    function setHash(tabName, replace) {
        const nextHash = `#${tabName}`;
        if (window.location.hash === nextHash) return;
        if (replace) {
            window.history.replaceState(null, '', nextHash);
        } else {
            window.history.pushState(null, '', nextHash);
        }
    }

    function activateTab(tabName, options = {}) {
        const requestedTab = getTab(tabName);
        const tab = requestedTab && !requestedTab.disabled ? requestedTab : getTab(DEFAULT_TAB);
        if (!tab) return;

        const selectedName = tab.dataset.lmTab;
        const isFirstActivation = !initializedTabs.has(selectedName);
        activeTab = selectedName;
        initializedTabs.add(selectedName);

        tabs.forEach(candidate => {
            const selected = candidate === tab;
            candidate.setAttribute('aria-selected', selected ? 'true' : 'false');
            candidate.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel, name) => {
            panel.hidden = name !== selectedName;
        });

        if (options.updateHash !== false) {
            setHash(selectedName, options.replaceHash === true);
        }
        if (options.focus === true) tab.focus();
        if (status && requestedTab?.disabled) {
            status.textContent = 'Digital twins and notifications are available only in Full Gateway mode.';
        } else if (status) {
            status.textContent = '';
        }

        document.dispatchEvent(new CustomEvent('lab-manager:tab-activated', {
            detail: { tab: selectedName, firstActivation: isFirstActivation }
        }));
    }

    function enabledTabs() {
        return tabs.filter(tab => !tab.disabled);
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', () => activateTab(tab.dataset.lmTab));
        tab.addEventListener('keydown', event => {
            const availableTabs = enabledTabs();
            const currentIndex = availableTabs.indexOf(tab);
            let nextIndex = null;
            if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % availableTabs.length;
            if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + availableTabs.length) % availableTabs.length;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = availableTabs.length - 1;
            if (nextIndex === null) return;
            event.preventDefault();
            activateTab(availableTabs[nextIndex].dataset.lmTab, { focus: true });
        });
    });

    window.addEventListener('hashchange', () => activateTab(tabFromHash(), { updateHash: false }));
    window.addEventListener('popstate', () => activateTab(tabFromHash(), { updateHash: false }));

    window.LabManagerTabs = Object.freeze({
        get activeTab() {
            return activeTab;
        },
        activateTab
    });

    loadGatewayMode().finally(() => {
        activateTab(tabFromHash(), { replaceHash: true });
    });

    async function loadGatewayMode() {
        try {
            const response = await fetch('/gateway/mode', {
                credentials: 'same-origin',
                cache: 'no-store',
                skipAuthPrompt: true
            });
            if (!response.ok) return;
            const mode = await response.json();
            if (!mode.lite) return;

            tabs
                .filter(tab => tab.matches('[data-full-only="true"]'))
                .forEach(tab => {
                    tab.disabled = true;
                    tab.setAttribute('aria-disabled', 'true');
                    tab.title = 'Available only in Full Gateway mode';
                });
            if (status) {
                status.textContent = 'Lite mode: Digital Twins and Notifications are unavailable.';
            }
        } catch (error) {
            console.warn('Gateway mode could not be determined; endpoint guards remain active.', error);
        }
    }
});
