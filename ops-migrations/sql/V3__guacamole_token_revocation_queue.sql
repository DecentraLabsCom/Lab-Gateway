-- Durable, encrypted revocation schedule for Guacamole auth tokens.

CREATE TABLE IF NOT EXISTS guacamole_token_revocation_queue (
    token_hash CHAR(64) NOT NULL,
    token_ciphertext TEXT NOT NULL,
    username VARCHAR(128) NOT NULL,
    reservation_key VARCHAR(80) NOT NULL,
    jwt_jti VARCHAR(128) NOT NULL,
    gateway_id VARCHAR(128) NOT NULL,
    expires_at DATETIME NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observed_at DATETIME NULL,
    revoked_at DATETIME NULL,
    last_error VARCHAR(1024) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (token_hash),
    KEY idx_guac_token_revocation_due (status, expires_at, next_attempt_at),
    KEY idx_guac_token_reconciliation (status, observed_at, expires_at)
);
