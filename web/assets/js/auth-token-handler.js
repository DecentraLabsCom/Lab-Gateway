/**
 * Authentication Token Handler
 * Intercepts 401 Unauthorized errors and provides a modal to input access tokens
 */

(function() {
    'use strict';

    // Token storage
    const TOKEN_STORAGE = {
        LAB_MANAGER: 'dlabs_lab_manager_token',
        SECURITY: 'dlabs_security_token',
        OPS: 'dlabs_ops_token'
    };

    // Token configuration based on path
    const TOKEN_CONFIG = {
        '/lab-manager': {
            key: TOKEN_STORAGE.LAB_MANAGER,
            header: 'X-Lab-Manager-Token',
            cookie: 'lab_manager_token',
            title: 'Lab Manager Access',
            description: 'This area requires a Lab Manager access token.'
        },
        '/wallet-dashboard': {
            key: TOKEN_STORAGE.SECURITY,
            header: 'X-Access-Token',
            cookie: 'access_token',
            title: 'Security Access',
            description: 'This area requires a security access token.'
        },
        '/institution-config': {
            key: TOKEN_STORAGE.SECURITY,
            header: 'X-Access-Token',
            cookie: 'access_token',
            title: 'Security Access',
            description: 'This area requires a security access token.'
        },
        '/ops-api': {
            key: TOKEN_STORAGE.OPS,
            header: 'X-Ops-Token',
            cookie: 'ops_token',
            title: 'Ops API Access',
            description: 'This area requires an Ops API access token.'
        }
    };

    // Create token modal HTML
    function createTokenModal() {
        if (document.getElementById('authTokenModal')) {
            return; // Modal already exists
        }

        const modalHTML = `
            <div id="authTokenModal" class="auth-token-modal" style="display: none;">
                <div class="auth-token-modal-overlay"></div>
                <div class="auth-token-modal-content">
                    <div class="auth-token-modal-header">
                        <h2 id="authTokenModalTitle">Access Token Required</h2>
                        <button class="auth-token-modal-close" id="authTokenModalClose">&times;</button>
                    </div>
                    <div class="auth-token-modal-body">
                        <p id="authTokenModalDescription">Please enter your access token to continue.</p>
                        <div class="auth-token-input-group">
                            <input 
                                type="password" 
                                id="authTokenInput" 
                                class="auth-token-input" 
                                placeholder="Enter access token..."
                                autocomplete="off"
                            />
                            <button type="button" id="authTokenToggle" class="auth-token-toggle" title="Show/Hide token">
                                <i class="fas fa-eye"></i>
                            </button>
                        </div>
                        <div class="auth-token-remember">
                            <label>
                                <input type="checkbox" id="authTokenRemember" checked>
                                Remember this token (stored locally)
                            </label>
                        </div>
                        <div id="authTokenError" class="auth-token-error" style="display: none;"></div>
                    </div>
                    <div class="auth-token-modal-footer">
                        <button id="authTokenCancel" class="auth-token-btn auth-token-btn-cancel">Cancel</button>
                        <button id="authTokenSubmit" class="auth-token-btn auth-token-btn-primary">Submit</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);
        attachModalEventListeners();
    }

    // Attach event listeners to modal
    function attachModalEventListeners() {
        const modal = document.getElementById('authTokenModal');
        const closeBtn = document.getElementById('authTokenModalClose');
        const cancelBtn = document.getElementById('authTokenCancel');
        const toggleBtn = document.getElementById('authTokenToggle');
        const input = document.getElementById('authTokenInput');

        closeBtn.addEventListener('click', hideTokenModal);
        cancelBtn.addEventListener('click', hideTokenModal);

        // Toggle password visibility
        toggleBtn.addEventListener('click', function() {
            const icon = this.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                icon.className = 'fas fa-eye-slash';
            } else {
                input.type = 'password';
                icon.className = 'fas fa-eye';
            }
        });

        // Close on overlay click
        modal.querySelector('.auth-token-modal-overlay').addEventListener('click', hideTokenModal);

        // Submit on Enter key
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                document.getElementById('authTokenSubmit').click();
            }
        });
    }

    // Show token modal
    function showTokenModal(config, callback) {
        createTokenModal();
        
        const modal = document.getElementById('authTokenModal');
        const title = document.getElementById('authTokenModalTitle');
        const description = document.getElementById('authTokenModalDescription');
        const input = document.getElementById('authTokenInput');
        const submitBtn = document.getElementById('authTokenSubmit');
        const errorDiv = document.getElementById('authTokenError');

        // Set content
        title.textContent = config.title;
        description.textContent = config.description;
        input.value = '';
        errorDiv.style.display = 'none';
        errorDiv.textContent = '';

        // Check for stored token
        const storedToken = localStorage.getItem(config.key);
        if (storedToken) {
            input.value = storedToken;
        }

        // Show modal
        modal.style.display = 'block';
        setTimeout(() => modal.classList.add('show'), 10);
        input.focus();

        // Handle submit
        submitBtn.onclick = function() {
            const token = input.value.trim();
            if (!token) {
                showError('Please enter a token');
                return;
            }

            const remember = document.getElementById('authTokenRemember').checked;
            if (remember) {
                localStorage.setItem(config.key, token);
            } else {
                localStorage.removeItem(config.key);
            }

            hideTokenModal();
            if (callback) {
                callback(token);
            }
        };
    }

    // Hide token modal
    function hideTokenModal() {
        const modal = document.getElementById('authTokenModal');
        if (modal) {
            modal.classList.remove('show');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 300);
        }
    }

    // Show error in modal
    function showError(message) {
        const errorDiv = document.getElementById('authTokenError');
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    // Get token config for current path
    function getTokenConfigForPath(path) {
        // Normalize path by removing trailing slash for comparison
        const normalizedPath = path.endsWith('/') && path !== '/' ? path.slice(0, -1) : path;
        
        for (const [prefix, config] of Object.entries(TOKEN_CONFIG)) {
            const normalizedPrefix = prefix.endsWith('/') ? prefix.slice(0, -1) : prefix;
            if (normalizedPath.startsWith(normalizedPrefix)) {
                return config;
            }
        }
        return null;
    }

    // Enhanced fetch wrapper
    function createAuthenticatedFetch() {
        const originalFetch = window.fetch;

        window.fetch = function(...args) {
            let [url, options = {}] = args;

            // Get current path
            const currentPath = window.location.pathname;
            const config = getTokenConfigForPath(currentPath);

            // Add stored token if available
            if (config) {
                const storedToken = localStorage.getItem(config.key);
                if (storedToken) {
                    options.headers = options.headers || {};
                    options.headers[config.header] = storedToken;
                }
            }

            // Execute original fetch
            return originalFetch(url, options)
                .then(response => {
                    // If 401 and we have config for this path
                    if (response.status === 401 && config) {
                        return new Promise((resolve, reject) => {
                            // Show modal and retry with token
                            showTokenModal(config, (token) => {
                                // Retry request with token
                                const retryOptions = { ...options };
                                retryOptions.headers = retryOptions.headers || {};
                                retryOptions.headers[config.header] = token;

                                originalFetch(url, retryOptions)
                                    .then(retryResponse => {
                                        if (retryResponse.status === 401) {
                                            // Token was wrong, remove from storage
                                            localStorage.removeItem(config.key);
                                            showError('Invalid token. Please try again.');
                                            reject(new Error('Authentication failed'));
                                        } else {
                                            resolve(retryResponse);
                                        }
                                    })
                                    .catch(reject);
                            });
                        });
                    }
                    return response;
                });
        };
    }

    // Handle clicks on protected links
    function handleProtectedLinks() {
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[href]');
            if (!link) return;

            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;

            const config = getTokenConfigForPath(href);
            if (!config) return;

            // Check if we have a stored token
            const storedToken = localStorage.getItem(config.key);
            if (!storedToken) {
                // Prevent navigation and show token modal
                e.preventDefault();
                showTokenModal(config, (token) => {
                    // Add token to URL and navigate
                    const separator = href.includes('?') ? '&' : '?';
                    window.location.href = `${href}${separator}token=${encodeURIComponent(token)}`;
                });
            } else {
                // Add token to URL if not already present
                if (!href.includes('token=')) {
                    e.preventDefault();
                    const separator = href.includes('?') ? '&' : '?';
                    window.location.href = `${href}${separator}token=${encodeURIComponent(storedToken)}`;
                }
            }
        });
    }

    // Extract token from URL query parameter and store it
    function extractTokenFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenFromUrl = urlParams.get('token');
        
        if (tokenFromUrl) {
            const config = getTokenConfigForPath(window.location.pathname);
            if (config) {
                // Store the token
                localStorage.setItem(config.key, tokenFromUrl);
                
                // Remove token from URL for security (clean URL)
                const url = new URL(window.location.href);
                url.searchParams.delete('token');
                window.history.replaceState({}, '', url.toString());
            }
        }
    }

    // Initialize on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            extractTokenFromUrl();
            createTokenModal();
            createAuthenticatedFetch();
            handleProtectedLinks();
        });
    } else {
        extractTokenFromUrl();
        createTokenModal();
        createAuthenticatedFetch();
        handleProtectedLinks();
    }

    // Export functions for manual use
    window.AuthTokenHandler = {
        showTokenModal,
        hideTokenModal,
        getTokenConfigForPath
    };

})();
