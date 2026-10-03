-- Durable local hand-off for observed Guacamole WebSocket openings.

CREATE TABLE IF NOT EXISTS gateway_session_observation_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dedup_key CHAR(64) NOT NULL,
    reservation_key VARCHAR(80) NOT NULL,
    jwt_jti VARCHAR(128) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    gateway_id VARCHAR(128) NOT NULL,
    access_type VARCHAR(32) NOT NULL,
    observed_at DATETIME NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1024) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_gateway_session_observation_dedup (dedup_key),
    KEY idx_gateway_session_observation_due (status, next_attempt_at, id),
    KEY idx_gateway_session_observation_lock (status, locked_at)
);
