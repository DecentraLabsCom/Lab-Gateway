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

    // Extract token from URL SYNCHRONOUSLY on page load
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenFromUrl = urlParams.get('token');
        
        if (tokenFromUrl) {
            const config = getTokenConfigForPath(window.location.pathname);
            if (config) {
                console.log('[AuthToken] Storing token from URL for', config.key);
                localStorage.setItem(config.key, tokenFromUrl);
                // Clean URL
                const url = new URL(window.location.href);
                url.searchParams.delete('token');
                window.history.replaceState({}, '', url.toString());
            }
        } else {
            // Check if we have token in storage
            const config = getTokenConfigForPath(window.location.pathname);
            if (config) {
                const stored = localStorage.getItem(config.key);
                console.log('[AuthToken] Token in localStorage:', stored ? 'YES' : 'NO');
            }
        }
    } catch (e) {
        console.error('[AuthToken] Error accessing localStorage:', e);
    }

    // Wrap fetch to add token header
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const config = getTokenConfigForPath(window.location.pathname);
        if (config) {
            const storedToken = localStorage.getItem(config.key);
            if (storedToken) {
                // Firefox compatibility: Handle both Headers instances and plain objects
                if (!options.headers) {
                    options.headers = {};
                }
                
                if (options.headers instanceof Headers) {
                    options.headers.set(config.header, storedToken);
                } else {
                    options.headers[config.header] = storedToken;
                }
                console.log('[AuthToken] Adding header', config.header, 'to fetch:', url);
            } else {
                console.warn('[AuthToken] No token found in localStorage for', config.key);
            }
        }
        
        return originalFetch.call(this, url, options);
    };

    console.log('[AuthToken] Fetch wrapper initialized');
})();
