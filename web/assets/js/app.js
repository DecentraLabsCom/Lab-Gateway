// Effects and animations for the main page
document.addEventListener('DOMContentLoaded', function() {
    let gatewayMode = 'full';

    function setGatewayMode(modeInfo) {
        const walletButton = document.getElementById('wallet-billing-btn');
        const mode = (modeInfo && modeInfo.mode ? String(modeInfo.mode) : '').toLowerCase();
        const lite = modeInfo && (modeInfo.lite === true || mode === 'lite');
        gatewayMode = lite ? 'lite' : 'full';

        if (lite) {
            if (walletButton) {
                walletButton.remove();
            }
            document.body.classList.add('gateway-lite-mode');
            return;
        }

        document.body.classList.remove('gateway-lite-mode');
    }

    function applyGatewayMode() {
        fetch('/gateway/mode', { cache: 'no-store' })
            .then(response => {
                if (!response.ok) {
                    return null;
                }
                return response.json();
            })
            .then(modeInfo => {
                if (!modeInfo) {
                    return;
                }
                setGatewayMode(modeInfo);
            })
            .catch(() => {
                // Fallback to aggregated health when /gateway/mode is unavailable.
                fetch('/gateway/health', { cache: 'no-store' })
                    .then(response => {
                        if (!response.ok) {
                            return null;
                        }
                        return response.json();
                    })
                    .then(healthInfo => {
                        if (!healthInfo) {
                            return;
                        }
                        setGatewayMode(healthInfo);
                    })
                    .catch(() => {
                        // Keep default UI if both mode endpoints are unavailable.
                    });
            });
    }
    
    applyGatewayMode();

    function installProtectedEntryHandlers() {
        const handler = window.AuthTokenHandler;
        if (!handler || typeof handler.getTokenConfigForPath !== 'function'
            || typeof handler.requestAuthenticationForPath !== 'function') {
            return;
        }

        document.querySelectorAll('.access-btn[href]').forEach(button => {
            const destination = new URL(button.href, window.location.origin);
            const config = handler.getTokenConfigForPath(destination.pathname);
            if (!config) return;

            button.addEventListener('click', event => {
                event.preventDefault();
                const checkPath = config.key === 'lab-manager'
                    ? '/lab-manager/access-policy'
                    : '/wallet-dashboard/';
                fetch(checkPath, {
                    credentials: 'same-origin',
                    cache: 'no-store',
                    skipAuthPrompt: true
                }).then(response => {
                    if (response.status === 401) {
                        handler.requestAuthenticationForPath(destination.pathname, () => {
                            window.location.assign(destination.href);
                        });
                        return;
                    }
                    window.location.assign(destination.href);
                }).catch(() => window.location.assign(destination.href));
            });
        });
    }

    installProtectedEntryHandlers();

    function handlePendingAuthentication() {
        const handler = window.AuthTokenHandler;
        const params = new URLSearchParams(window.location.search);
        const scope = params.get('auth');
        const nextValue = params.get('next');
        if (!handler || !scope || !nextValue) return;

        let destination;
        try {
            destination = new URL(nextValue, window.location.origin);
        } catch (_) {
            return;
        }
        if (destination.origin !== window.location.origin
            || !['/lab-manager/', '/wallet-dashboard/'].includes(destination.pathname)) {
            return;
        }
        const config = handler.getTokenConfigForPath(destination.pathname);
        if (!config || config.key !== scope) return;

        window.history.replaceState({}, document.title, window.location.pathname);
        const checkPath = scope === 'lab-manager' ? '/lab-manager/access-policy' : '/wallet-dashboard/';
        fetch(checkPath, {
            credentials: 'same-origin',
            cache: 'no-store',
            skipAuthPrompt: true
        }).then(response => {
            if (response.status === 401) {
                handler.requestAuthenticationForPath(destination.pathname, () => {
                    window.location.assign(destination.href);
                });
                return;
            }
            window.location.assign(destination.href);
        }).catch(() => window.location.assign(destination.href));
    }

    handlePendingAuthentication();

    document.querySelectorAll('[data-external-url]').forEach(button => {
        button.addEventListener('click', () => window.open(button.dataset.externalUrl, '_blank', 'noopener,noreferrer'));
    });
    
    // Entry animation for elements
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Apply animation to feature cards
    const featureCards = document.querySelectorAll('.feature-card');
    featureCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(30px)';
        card.style.transition = `opacity 0.6s ease ${index * 0.2}s, transform 0.6s ease ${index * 0.2}s`;
        observer.observe(card);
    });

    // Access panel animation
    const accessPanel = document.querySelector('.access-panel');
    if (accessPanel) {
        accessPanel.style.opacity = '0';
        accessPanel.style.transform = 'translateY(20px)';
        accessPanel.style.transition = 'opacity 0.8s ease 0.3s, transform 0.8s ease 0.3s';
        observer.observe(accessPanel);
    }

    // Enhanced hover effect for buttons
    const accessButtons = document.querySelectorAll('.access-btn');
    accessButtons.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px) scale(1.02)';
        });
        
        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });

    // Status indicator animation
    const statusDot = document.querySelector('.status-dot');
    if (statusDot) {
        setInterval(() => {
            statusDot.style.animation = 'none';
            statusDot.offsetHeight; // Trigger reflow
            const statusIndicator = statusDot.closest('.status-indicator');
            if (statusIndicator.classList.contains('online')) {
                statusDot.style.animation = 'pulse-dot-online 2s infinite';
            } else if (statusIndicator.classList.contains('partial')) {
                statusDot.style.animation = 'pulse-dot-partial 2s infinite';
            } else if (statusIndicator.classList.contains('checking')) {
                statusDot.style.animation = 'pulse-dot-checking 2s infinite';
            } else if (statusIndicator.classList.contains('unknown')) {
                statusDot.style.animation = 'pulse-dot-checking 2s infinite';
            } else {
                statusDot.style.animation = 'pulse-dot-offline 2s infinite';
            }
        }, 10000);
    }

    // Status detail modal - creates and appends modal to DOM
    createStatusModal();
    let lastStatusDetails = { ok: [], missing: [], status: '' };

    function renderDetailedStatus(data, statusIndicator, statusText) {
        const services = data.services || {};
        const blockchain = services.blockchain || {};
        const guacamole = services.guacamole || {};
        const guacApi = services.guacamole_api || {};
        const ops = services.ops || {};
        const mysql = services.mysql || {};
        const liteAuth = services.lite_auth || {};
        const mode = (data.mode || gatewayMode || 'full').toString().toLowerCase();
        const liteMode = data.lite === true || mode === 'lite';
        const statusValue = (data.status || '').toString().toUpperCase();

        const okItems = [];
        const missingItems = [];
        const labServices = [
            guacamole,
            guacApi,
            services.guacd || {},
            services.guacamole_schema || {},
            mysql
        ];
        const operationalLabServices = labServices.filter(service => service.ok === true).length;
        const labsOk = operationalLabServices === labServices.length;

        if (liteMode) {
            setGatewayMode({ mode: 'lite', lite: true });
            if (liteAuth.ok === true) {
                okItems.push('Lite issuer/public key trust operative');
            } else {
                missingItems.push({ text: 'Lite issuer/public key trust failed', href: '/gateway-health/' });
            }
        } else if (blockchain.ok === true) {
            okItems.push('Blockchain services operative');
        } else {
            const blockchainStatus = (blockchain.details?.status || blockchain.status || '').toString().toUpperCase();
            const blockchainReachable = blockchain.reachable === true
                || (typeof blockchain.status === 'number' && blockchain.status < 500);
            missingItems.push({
                text: blockchainReachable || blockchainStatus === 'DEGRADED' || blockchainStatus === 'PARTIAL'
                    ? 'Blockchain services degraded'
                    : 'Blockchain services inoperative',
                href: '/gateway-health/'
            });
        }

        if (labsOk) {
            okItems.push('Labs access operative');
        } else {
            missingItems.push({
                text: operationalLabServices > 0 ? 'Labs access degraded' : 'Labs access inoperative',
                href: '/gateway-health/'
            });
        }

        if (ops.ok === false) {
            missingItems.push({ text: 'Ops worker inoperative', href: '/gateway-health/' });
        }

        const fmuRunner = services.fmu_runner || {};
        if (fmuRunner.enabled === true) {
            if (fmuRunner.ok === true) {
                okItems.push('FMU runner operative');
            } else {
                const fmuStatus = (fmuRunner.details?.status || fmuRunner.status || '').toString().toUpperCase();
                missingItems.push({
                    text: fmuStatus === 'DEGRADED' || fmuStatus === 'PARTIAL' ? 'FMU runner degraded' : 'FMU runner inoperative',
                    href: '/gateway-health/'
                });
            }
        }

        const aas = services.aas || {};
        if (aas.enabled === true) {
            if (aas.ok === true) {
                okItems.push('AAS server operative');
            } else {
                missingItems.push({ text: 'AAS server inoperative', href: '/gateway-health/' });
            }
        }

        if (statusValue === 'UP') {
            statusIndicator.className = 'status-indicator online';
            statusText.textContent = 'Gateway Online';
        } else if (statusValue === 'PARTIAL') {
            statusIndicator.className = 'status-indicator partial';
            statusText.textContent = 'Gateway Partially Available';
        } else {
            statusIndicator.className = 'status-indicator offline';
            statusText.textContent = 'Gateway Unavailable';
        }
        statusIndicator.setAttribute('title', 'Click for status details');
        lastStatusDetails = {
            status: statusText.textContent,
            ok: okItems,
            missing: missingItems
        };
    }

    // System status monitoring - checks Guacamole and blockchain-services (incl. keys)
    function updateSystemStatus() {
        const statusIndicator = document.querySelector('.status-indicator');
        if (!statusIndicator) return;
        const statusText = statusIndicator.querySelector('.status-text');
        if (!statusText) return;

        statusIndicator.className = 'status-indicator checking';
        statusText.textContent = 'Checking Status...';

        fetch('/gateway/health')
            .then(async response => {
                const body = await response.text();
                let data = {};
                try {
                    data = body ? JSON.parse(body) : {};
                } catch (e) {
                    data = { parseError: e.message };
                }

                if (data.parseError || !data.status) {
                    statusIndicator.className = 'status-indicator unknown';
                    statusText.textContent = 'Status Unknown';
                    statusIndicator.setAttribute('title', 'Click for status details');
                    lastStatusDetails = {
                        status: 'Status Unknown',
                        ok: [],
                        missing: ['Unable to interpret current status']
                    };
                    return;
                }

                // The public endpoint is intentionally aggregate-only. Do not
                // mark every hidden service as failed when details are redacted.
                if (data.public === true) {
                    const publicStatus = (data.status || '').toString().toUpperCase();
                    if (publicStatus === 'UP') {
                        statusIndicator.className = 'status-indicator unknown';
                        statusText.textContent = 'Gateway Online · Config. Unknown';
                    } else if (publicStatus === 'PARTIAL') {
                        statusIndicator.className = 'status-indicator partial';
                        statusText.textContent = 'Gateway Partially Available · Config. Unknown';
                    } else {
                        statusIndicator.className = 'status-indicator offline';
                        statusText.textContent = 'Gateway Unavailable';
                    }
                    statusIndicator.setAttribute('title', 'Click for status details');
                    lastStatusDetails = {
                        status: statusText.textContent,
                        ok: publicStatus === 'UP' ? ['Public readiness operative'] : [],
                        missing: [{
                            text: 'Configuration status requires operator authentication',
                            href: '/gateway-health/',
                            authPath: '/lab-manager/'
                        }]
                    };
                    fetch('/gateway/health/details', {
                        credentials: 'same-origin',
                        cache: 'no-store',
                        skipAuthPrompt: true
                    }).then(detailsResponse => {
                        if (detailsResponse.status === 401 || detailsResponse.status === 403) return null;
                        return detailsResponse.json().catch(() => null);
                    }).then(details => {
                        if (details && details.public !== true) {
                            renderDetailedStatus(details, statusIndicator, statusText);
                        }
                    }).catch(() => {});
                    return;
                }

                renderDetailedStatus(data, statusIndicator, statusText);
            })
            .catch(() => {
                statusIndicator.className = 'status-indicator unknown';
                statusText.textContent = 'Status Unknown';
                lastStatusDetails = {
                    status: 'Status Unknown',
                    ok: [],
                    missing: ['Unable to retrieve current status']
                };
            });
    }
// Check status every 30 seconds
    updateSystemStatus();
    setInterval(updateSystemStatus, 30000);

    // Glow effect on logos
    const logos = document.querySelectorAll('.logo');
    logos.forEach(logo => {
        logo.addEventListener('mouseenter', function() {
            this.style.filter = 'drop-shadow(0 0 20px rgba(0, 245, 255, 0.8)) brightness(1.2)';
        });
        
        logo.addEventListener('mouseleave', function() {
            this.style.filter = 'drop-shadow(0 0 10px rgba(0, 245, 255, 0.5)) brightness(1)';
        });
    });

    // Add class to indicate JavaScript is loaded
    document.body.classList.add('js-loaded');

    const statusIndicator = document.querySelector('.status-indicator');
    if (statusIndicator) {
        statusIndicator.addEventListener('click', () => {
            openStatusModal(lastStatusDetails);
        });
        statusIndicator.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openStatusModal(lastStatusDetails);
            }
        });
    }

    console.log('🚀 DecentraLabs Gateway - System started');
    console.log('🔗 Developed by Nebulous Systems');
    // FMU access flow: detect ?jwt= param and render access panel if applicable
    const urlParams = new URLSearchParams(window.location.search);
    const jwtParam = urlParams.get('jwt');
    if (jwtParam) {
        const fmuClaims = tryDecodeFmuJwt(jwtParam);
        if (fmuClaims && fmuClaims.resourceType === 'fmu') {
            showFmuAccessPanel(fmuClaims, jwtParam);
        }
    }});

function createStatusModal() {
    const modal = document.createElement('div');
    modal.className = 'status-modal';
    modal.innerHTML = `
        <div class="backdrop"></div>
        <div class="content">
            <div class="header">
                <h3>System status details</h3>
                <button class="close-btn" type="button">&times;</button>
            </div>
            <div class="columns">
                <div class="col ok">
                    <h4>Working</h4>
                    <ul class="ok-list"></ul>
                </div>
                <div class="col bad">
                    <h4>Issues</h4>
                    <ul class="bad-list"></ul>
                </div>
            </div>
            <div class="modal-actions">
                <a class="primary-btn" href="/gateway-health/" target="_blank" rel="noreferrer">More info</a>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const close = () => modal.classList.remove('show');
    modal.querySelector('.backdrop').addEventListener('click', close);
    modal.querySelector('.close-btn').addEventListener('click', close);
    return modal;
}

function openStatusModal(details) {
    const modal = document.querySelector('.status-modal');
    if (!modal) return;
    const okList = modal.querySelector('.ok-list');
    const badList = modal.querySelector('.bad-list');
    okList.innerHTML = '';
    badList.innerHTML = '';

    const okItems = Array.isArray(details.ok) && details.ok.length ? details.ok : ['No additional checks passed'];
    const badItems = Array.isArray(details.missing) && details.missing.length ? details.missing : ['No outstanding issues'];

    const appendStatusItem = (list, item) => {
        const li = document.createElement('li');
        if (typeof item === 'object' && item !== null && item.href) {
            const link = document.createElement('a');
            link.href = item.href;
            link.textContent = item.text || item.href;
            if (item.authPath) {
                link.addEventListener('click', event => {
                    event.preventDefault();
                    const authenticationPath = item.authPath;
                    const destination = item.href || authenticationPath;
                    const accessPolicy = fetch('/lab-manager/access-policy', {
                        credentials: 'same-origin',
                        cache: 'no-store',
                        skipAuthPrompt: true
                    });
                    accessPolicy.then(response => {
                        if (response.ok) {
                            window.location.assign(destination);
                            return;
                        }
                        if (response.status === 401 && window.AuthTokenHandler?.requestAuthenticationForPath) {
                            window.AuthTokenHandler.requestAuthenticationForPath(authenticationPath, () => {
                                window.location.assign(destination);
                            });
                            return;
                        }
                        window.location.assign(destination);
                    }).catch(() => window.location.assign(destination));
                });
            }
            li.appendChild(link);
        } else {
            li.textContent = typeof item === 'object' && item !== null ? (item.text || '') : item;
        }
        list.appendChild(li);
    };

    okItems.forEach(item => appendStatusItem(okList, item));
    badItems.forEach(item => appendStatusItem(badList, item));

    modal.classList.add('show');
}

// Function to show authentication service information
function showAuthServiceInfo() {
    const modal = document.createElement('div');
    modal.className = 'auth-modal';
    modal.innerHTML = `
        <div class="auth-modal-content">
            <div class="auth-modal-header">
                <h3>🔐 Authentication Service</h3>
                <button class="close-modal" data-close-auth type="button">&times;</button>
            </div>
            <div class="auth-modal-body">
                <div class="auth-info">
                    <div class="auth-status">
                        <span class="status-icon">⚠️</span>
                        <span class="status-message">Lite mode uses an external issuer</span>
                    </div>
                    <p>In <strong>Lite</strong> mode this gateway trusts JWTs issued by an external <strong>Full Gateway</strong> or compatible issuer instead of exposing its own provider authentication endpoints.</p>
                    
                    <div class="comparison-table">
                        <div class="comparison-row header">
                            <div class="feature-name">Feature</div>
                            <div class="lite-version">Lite</div>
                            <div class="full-version">Full</div>
                        </div>
                        <div class="comparison-row">
                            <div class="feature-name">Laboratory Access</div>
                            <div class="lite-version">✅</div>
                            <div class="full-version">✅</div>
                        </div>
                        <div class="comparison-row">
                            <div class="feature-name">Basic Authentication</div>
                            <div class="lite-version">✅</div>
                            <div class="full-version">✅</div>
                        </div>
                        <div class="comparison-row">
                            <div class="feature-name">JWT Auth2 Service</div>
                            <div class="lite-version">❌</div>
                            <div class="full-version">✅</div>
                        </div>
                        <div class="comparison-row">
                            <div class="feature-name">Blockchain-backed access</div>
                            <div class="lite-version">✅</div>
                            <div class="full-version">✅</div>
                        </div>
                    </div>
                    
                    <div class="auth-actions">
                        <a href="https://github.com/DecentraLabsCom/lite-lab-gateway" target="_blank" rel="noopener noreferrer" class="upgrade-button">
                            <span class="btn-icon">📦</span>
                            <span class="btn-text">Download Full Version</span>
                            <span class="btn-arrow">↗</span>
                        </a>
                        <p class="auth-note">The Full Version exposes the local provider auth surface. Lite keeps lab access and FMU access, but trusts an external issuer for JWT validation.</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="auth-modal-overlay" data-close-auth></div>
    `;
    
    document.body.appendChild(modal);
    modal.querySelectorAll('[data-close-auth]').forEach(node => node.addEventListener('click', closeAuthModal));
    document.body.style.overflow = 'hidden';
    
    // Animation
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

// Function to close authentication modal
function closeAuthModal() {
    const modal = document.querySelector('.auth-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(modal);
            document.body.style.overflow = '';
        }, 300);
    }
}

// Function to show version information modal
function showVersionInfo() {
    const modal = document.createElement('div');
    modal.className = 'version-modal';
    modal.innerHTML = `
        <div class="version-modal-content">
            <div class="version-modal-header">
                <h3>📋 Version Information</h3>
                <button class="close-modal" data-close-version type="button">&times;</button>
            </div>
            <div class="version-modal-body">
                <div class="version-info-modal">
                    <div class="version-card lite">
                        <h3>🚀 Lite Version</h3>
                        <p>Currently running the <strong>Lite</strong> gateway mode, delegating JWT issuance to an external Full Gateway or compatible issuer.</p>
                        <ul>
                            <li>✅ Direct lab access via Guacamole</li>
                            <li>✅ Basic authentication</li>
                            <li>✅ Encrypted connections</li>
                            <li>❌ Local provider auth endpoints</li>
                            <li>✅ JWT-based lab and FMU access via external issuer</li>
                        </ul>
                    </div>
                    
                    <div class="version-card full">
                        <h3>🔧 Full Version Available</h3>
                        <p>Want the complete authentication service and user management?</p>
                        <a href="https://github.com/DecentraLabsCom/full-lab-gateway" target="_blank" rel="noopener noreferrer" class="upgrade-btn">
                            <span class="btn-icon">📦</span>
                            <span class="btn-text">Download Full Version</span>
                            <span class="btn-arrow">↗</span>
                        </a>
                        <p class="upgrade-note">Includes the local provider authentication surface, OIDC/JWKS endpoints, and the full provider publication stack.</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="version-modal-overlay" data-close-version></div>
    `;
    
    document.body.appendChild(modal);
    modal.querySelectorAll('[data-close-version]').forEach(node => node.addEventListener('click', closeVersionModal));
    document.body.style.overflow = 'hidden';
    
    // Animation
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

// Function to close version modal
function closeVersionModal() {
    const modal = document.querySelector('.version-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(modal);
            document.body.style.overflow = '';
        }, 300);
    }
}
