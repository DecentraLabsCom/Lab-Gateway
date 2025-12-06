// Effects and animations for the main page
document.addEventListener('DOMContentLoaded', function() {
    
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
            } else {
                statusDot.style.animation = 'pulse-dot-offline 2s infinite';
            }
        }, 10000);
    }

    // Status detail modal - creates and appends modal to DOM
    createStatusModal();
    let lastStatusDetails = { ok: [], missing: [], status: '' };

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

                const services = data.services || {};
                const blockchain = services.blockchain || {};
                const guacamole = services.guacamole || {};
                const guacApi = services.guacamole_api || {};
                const ops = services.ops || {};
                const mysql = services.mysql || {};
                const statusValue = (data.status || '').toString().toUpperCase();

                const okItems = [];
                const missingItems = [];

                const labsOk = guacamole.ok === true && guacApi.ok === true && mysql.ok === true;

                if (blockchain.ok === true) {
                    okItems.push('Blockchain services operative');
                } else {
                    missingItems.push({ text: `Blockchain services inoperative`, href: '/gateway-health/' });
                }

                if (labsOk) {
                    okItems.push('Labs access operative');
                } else {
                    missingItems.push({ text: `Labs access inoperative`, href: '/gateway-health/' });
                }

                if (ops.ok === false) {
                    missingItems.push({ text: 'Ops worker inoperative', href: '/gateway-health/' });
                }

                if (statusValue === 'UP') {
                    statusIndicator.className = 'status-indicator online';
                    statusText.textContent = 'System Online';
                    statusIndicator.removeAttribute('title');
                } else if (statusValue === 'PARTIAL') {
                    statusIndicator.className = 'status-indicator partial';
                    statusIndicator.setAttribute('title', 'Click for status details');
                    statusText.textContent = 'Partial';
                } else {
                    statusIndicator.className = 'status-indicator offline';
                    statusIndicator.setAttribute('title', 'Click for status details');
                    statusText.textContent = 'System Unavailable';
                }

                lastStatusDetails = {
                    status: statusText.textContent,
                    ok: okItems,
                    missing: missingItems
                };
            })
            .catch(() => {
                statusIndicator.className = 'status-indicator checking';
                statusText.textContent = 'Checking Status...';
                lastStatusDetails = {
                    status: 'Checking Status...',
                    ok: [],
                    missing: ['Awaiting latest status']
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
            const isPartial = statusIndicator.classList.contains('partial');
            const isOffline = statusIndicator.classList.contains('offline');
            if (isPartial || isOffline) {
                openStatusModal(lastStatusDetails);
            }
        });
    }

    console.log('🚀 DecentraLabs Gateway - System started');
    console.log('🔗 Developed by Nebulous Systems');
});

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

    okItems.forEach(item => {
        const li = document.createElement('li');
        li.textContent = typeof item === 'object' && item !== null ? (item.text || '') : item;
        okList.appendChild(li);
    });
    badItems.forEach(item => {
        const li = document.createElement('li');
        li.textContent = typeof item === 'object' && item !== null ? (item.text || '') : item;
        badList.appendChild(li);
    });

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
                <button class="close-modal" onclick="closeAuthModal()">&times;</button>
            </div>
            <div class="auth-modal-body">
                <div class="auth-info">
                    <div class="auth-status">
                        <span class="status-icon">⚠️</span>
                        <span class="status-message">Not Available in Lite Version</span>
                    </div>
                    <p>The advanced authentication service is only available in the <strong>Full Version</strong> of DecentraLabs Gateway.</p>
                    
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
                            <div class="feature-name">Blockchain Integration</div>
                            <div class="lite-version">❌</div>
                            <div class="full-version">✅</div>
                        </div>
                    </div>
                    
                    <div class="auth-actions">
                        <a href="https://github.com/DecentraLabsCom/lite-lab-gateway" target="_blank" rel="noopener noreferrer" class="upgrade-button">
                            <span class="btn-icon">📦</span>
                            <span class="btn-text">Download Full Version</span>
                            <span class="btn-arrow">↗</span>
                        </a>
                        <p class="auth-note">The Full Version includes a complete authentication and authorization microservice, JWT token handling, and blockchain integration capabilities.</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="auth-modal-overlay" onclick="closeAuthModal()"></div>
    `;
    
    document.body.appendChild(modal);
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
                <button class="close-modal" onclick="closeVersionModal()">&times;</button>
            </div>
            <div class="version-modal-body">
                <div class="version-info-modal">
                    <div class="version-card lite">
                        <h3>🚀 Lite Version</h3>
                        <p>Currently running the <strong>Lite</strong> version with core laboratory access functionality.</p>
                        <ul>
                            <li>✅ Direct lab access via Guacamole</li>
                            <li>✅ Basic authentication</li>
                            <li>✅ Encrypted connections</li>
                            <li>❌ Authentication & authorization service</li>
                            <li>❌ Blockchain integration</li>
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
                        <p class="upgrade-note">Includes distributed authentication service and blockchain integration.</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="version-modal-overlay" onclick="closeVersionModal()"></div>
    `;
    
    document.body.appendChild(modal);
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
