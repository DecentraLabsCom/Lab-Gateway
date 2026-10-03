-- Durable power operation detail and idempotency.
-- Controller, outlet and policy definitions remain JSON-backed in the first
-- implementation slice and can be normalized in a later migration.

CREATE TABLE IF NOT EXISTS power_operations (
    id BIGINT NOT NULL AUTO_INCREMENT,
    reservation_id VARCHAR(128),
    lab_id VARCHAR(128),
    policy_id VARCHAR(128),
    step_id VARCHAR(128),
    phase VARCHAR(32),
    controller_id VARCHAR(128) NOT NULL,
    outlet_key VARCHAR(64) NOT NULL,
    action VARCHAR(32) NOT NULL,
    requested_state VARCHAR(32),
    observed_state_before VARCHAR(32),
    observed_state_after VARCHAR(32),
    status VARCHAR(32) NOT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    response_code INT,
    duration_ms INT,
    idempotency_key VARCHAR(255) NOT NULL,
    payload JSON,
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_power_idempotency (idempotency_key),
    KEY idx_power_reservation (reservation_id, phase),
    KEY idx_power_lab_time (lab_id, created_at)
);
