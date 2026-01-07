/**
 * Authentication Token Fetch Wrapper (Lite version - no modal)
 * Only adds stored token to fetch requests
 */

(function() {
    'use strict';

    const TOKEN_CONFIG = {
        '/lab-manager': {
            key: 'dlabs_lab_manager_token',
            header: 'X-Lab-Manager-Token'
        },
        '/wallet-dashboard': {
            key: 'dlabs_security_token',
            header: 'X-Access-Token'
        },
        '/institution-config': {
            key: 'dlabs_security_token',
            header: 'X-Access-Token'
        }
    };

    function getTokenConfigForPath(path) {
        const normalizedPath = path.endsWith('/') && path !== '/' ? path.slice(0, -1) : path;
        for (const [prefix, config] of Object.entries(TOKEN_CONFIG)) {
            const normalizedPrefix = prefix.endsWith('/') ? prefix.slice(0, -1) : prefix;
            if (normalizedPath.startsWith(normalizedPrefix)) {
                return config;
            }
        }
        return null;
    }

    // Extract token from URL on page load and store it
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get('token');
    
    if (tokenFromUrl) {
        const config = getTokenConfigForPath(window.location.pathname);
        if (config) {
            localStorage.setItem(config.key, tokenFromUrl);
            // Clean URL
            const url = new URL(window.location.href);
            url.searchParams.delete('token');
            window.history.replaceState({}, '', url.toString());
        }
    }

    // Wrap fetch to add token header
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        let [url, options = {}] = args;
        
        const config = getTokenConfigForPath(window.location.pathname);
        if (config) {
            const storedToken = localStorage.getItem(config.key);
            if (storedToken) {
                options.headers = options.headers || {};
                options.headers[config.header] = storedToken;
            }
        }
        
        return originalFetch(url, options);
    };
})();
