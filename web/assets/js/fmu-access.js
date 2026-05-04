// ─── FMU Access Panel ────────────────────────────────────────────────────────
// Handles the ?jwt= redirect from the Marketplace for FMU reservations.
// Loaded after app.js; functions are called from app.js DOMContentLoaded.

/**
 * Decode a JWT payload without verification (display only — the server validates the sig).
 * Returns null if the token is malformed.
 */
function tryDecodeFmuJwt(token) {
    try {
        const parts = token.split('.');
        if (parts.length !== 3) return null;
        const padded = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const json = atob(padded + '=='.slice((padded.length + 3) % 4 === 0 ? 2 : (padded.length % 4)));
        return JSON.parse(json);
    } catch (_) {
        return null;
    }
}

/**
 * Replace the main hero section with a self-contained FMU access panel.
 */
function showFmuAccessPanel(claims, rawJwt) {
    const heroSection = document.querySelector('.hero-section');
    if (!heroSection) return;

    const modelName = claims.accessKey || claims.sub || 'Unknown model';
    const labId = claims.labId != null ? String(claims.labId) : null;
    const reservationKey = claims.reservationKey || null;
    const expTs = claims.exp ? Number(claims.exp) : null;

    // Build download URL — gateway public path: /fmu/api/v1/fmu/proxy/{labId}
    let downloadUrl = null;
    if (labId) {
        downloadUrl = '/fmu/api/v1/fmu/proxy/' + encodeURIComponent(labId);
        if (reservationKey) {
            downloadUrl += '?reservationKey=' + encodeURIComponent(reservationKey);
        }
    }

    const displayName = modelName.replace(/\.fmu$/i, '');

    heroSection.innerHTML = `
        <div class="fmu-access-panel">
            <div class="fmu-header">
                <div class="fmu-icon"><i class="fas fa-cube"></i></div>
                <div class="fmu-title-block">
                    <h1 class="fmu-model-name">${escHtml(displayName)}</h1>
                    <span class="fmu-badge"><i class="fas fa-microchip"></i> FMU Simulation</span>
                </div>
            </div>

            <div class="fmu-meta-row">
                <div class="fmu-meta-item">
                    <span class="fmu-meta-label"><i class="fas fa-tag"></i> Access key</span>
                    <span class="fmu-meta-value">${escHtml(modelName)}</span>
                </div>
                ${labId ? `<div class="fmu-meta-item">
                    <span class="fmu-meta-label"><i class="fas fa-flask"></i> Lab ID</span>
                    <span class="fmu-meta-value">${escHtml(labId)}</span>
                </div>` : ''}
                ${reservationKey ? `<div class="fmu-meta-item fmu-meta-key">
                    <span class="fmu-meta-label"><i class="fas fa-key"></i> Reservation</span>
                    <span class="fmu-meta-value fmu-mono">${escHtml(reservationKey.slice(0, 18))}\u2026</span>
                </div>` : ''}
            </div>

            <div id="fmu-timer-block" class="fmu-timer-block">
                <span class="fmu-timer-label"><i class="fas fa-clock"></i> Session expires in</span>
                <span id="fmu-countdown" class="fmu-countdown">—</span>
            </div>

            ${!reservationKey ? `<div class="fmu-warning">
                <i class="fas fa-triangle-exclamation"></i>
                <span>This token does not include a <code>reservationKey</code>. Re-open access from the Marketplace to get an updated token.</span>
            </div>` : ''}

            <div class="fmu-download-block">
                <button id="fmu-download-btn" class="fmu-download-btn" ${!downloadUrl ? 'disabled' : ''}>
                    <i class="fas fa-download"></i>
                    <span>Download proxy.fmu</span>
                </button>
                <div id="fmu-download-status" class="fmu-download-status" style="display:none;"></div>
            </div>

            <div class="fmu-instructions">
                <h3><i class="fas fa-circle-info"></i> What to do with this file</h3>
                <ol class="fmu-steps">
                    <li>
                        <span class="step-num">1</span>
                        <div>
                            <strong>Download</strong> <code>proxy.fmu</code> using the button above.
                            This is a connector — it does not contain the real simulation model.
                        </div>
                    </li>
                    <li>
                        <span class="step-num">2</span>
                        <div>
                            <strong>Open in OpenModelica:</strong> File &rarr; Import FMU &rarr; select <code>proxy.fmu</code>.
                            When you run a simulation OMEdit will connect to this gateway in real time.
                        </div>
                    </li>
                    <li>
                        <span class="step-num">3</span>
                        <div>
                            <strong>Alternative — FMPy (Python):</strong>
                            <code class="fmu-code-block">pip install fmpy\npython -m fmpy simulate proxy.fmu</code>
                        </div>
                    </li>
                    <li>
                        <span class="step-num">4</span>
                        <div>
                            <strong>Time limit:</strong> the proxy.fmu is valid only while your reservation is active.
                            When the timer above reaches zero the gateway will close the session.
                        </div>
                    </li>
                </ol>
            </div>

            <div class="fmu-footer-note">
                <i class="fas fa-shield-halved"></i>
                The real simulation model runs on the provider's infrastructure and never leaves it.
                Your proxy.fmu only contains the interface and a secure one-time session token.
            </div>
        </div>
    `;

    // Wire download button
    if (downloadUrl) {
        document.getElementById('fmu-download-btn').addEventListener('click', function () {
            triggerFmuDownload(downloadUrl, rawJwt, modelName);
        });
    }

    // Start countdown
    if (expTs) {
        startFmuCountdown(expTs);
    }
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function startFmuCountdown(expTs) {
    const el = document.getElementById('fmu-countdown');
    if (!el) return;

    function tick() {
        const remaining = expTs - Math.floor(Date.now() / 1000);
        if (remaining <= 0) {
            el.textContent = 'Expired';
            el.classList.add('fmu-countdown-expired');
            const btn = document.getElementById('fmu-download-btn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-ban"></i><span>Session expired</span>';
            }
            return;
        }

        const h = Math.floor(remaining / 3600);
        const m = Math.floor((remaining % 3600) / 60);
        const s = remaining % 60;
        el.textContent = h > 0
            ? `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`
            : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

        el.classList.toggle('fmu-countdown-warning', remaining <= 120);
        setTimeout(tick, 1000);
    }

    tick();
}

function triggerFmuDownload(url, jwt, modelName) {
    const btn = document.getElementById('fmu-download-btn');
    const statusEl = document.getElementById('fmu-download-status');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Downloading…</span>';
    }

    fetch(url, { headers: { 'Authorization': 'Bearer ' + jwt } })
        .then(res => {
            if (!res.ok) throw new Error('Server returned ' + res.status);
            return res.blob();
        })
        .then(blob => {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = (modelName || 'proxy') + '.fmu';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);

            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-download"></i><span>Download proxy.fmu</span>';
            }
            if (statusEl) {
                statusEl.className = 'fmu-download-status fmu-download-ok';
                statusEl.innerHTML = '<i class="fas fa-circle-check"></i> File downloaded successfully.';
                statusEl.style.display = 'flex';
            }
        })
        .catch(err => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-download"></i><span>Download proxy.fmu</span>';
            }
            if (statusEl) {
                statusEl.className = 'fmu-download-status fmu-download-err';
                statusEl.innerHTML = '<i class="fas fa-circle-xmark"></i> Download failed: ' + escHtml(err.message);
                statusEl.style.display = 'flex';
            }
        });
}
