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
            } else {
                statusDot.style.animation = 'pulse-dot-offline 2s infinite';
            }
        }, 10000);
    }

    // System status monitoring - checks both Guacamole and blockchain-services
    function updateSystemStatus() {
        const statusIndicator = document.querySelector('.status-indicator');
        const statusText = statusIndicator.querySelector('.status-text');
        
        // Check both services in parallel
        Promise.all([
            fetch('/guacamole/')
                .then(response => ({ service: 'guacamole', ok: response.ok }))
                .catch(() => ({ service: 'guacamole', ok: false })),
            fetch('/health')
                .then(response => response.ok ? response.json() : Promise.reject())
                .then(data => ({ service: 'blockchain', ok: data.status === 'UP' || data.status === 'DEGRADED' }))
                .catch(() => ({ service: 'blockchain', ok: false }))
        ])
        .then(results => {
            const guacamoleOk = results[0].ok;
            const blockchainOk = results[1].ok;
            
            if (guacamoleOk && blockchainOk) {
                statusIndicator.className = 'status-indicator online';
                statusText.textContent = 'System Online';
            } else if (guacamoleOk || blockchainOk) {
                statusIndicator.className = 'status-indicator online';
                const availableServices = [];
                if (guacamoleOk) availableServices.push('Labs');
                if (blockchainOk) availableServices.push('Blockchain');
                statusText.textContent = `Partial: ${availableServices.join(', ')}`;
            } else {
                statusIndicator.className = 'status-indicator offline';
                statusText.textContent = 'System Unavailable';
            }
        })
        .catch(() => {
            statusIndicator.className = 'status-indicator offline';
            statusText.textContent = 'Checking Status...';
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

    console.log('🚀 DecentraLabs Gateway - System started');
    console.log('🔗 Developed by Nebulous Systems');
});

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
