-- Intents persistence (idempotencia y reconciliacion)
CREATE TABLE IF NOT EXISTS intents (
    request_id VARCHAR(66) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    action VARCHAR(64),
    provider VARCHAR(66),
    lab_id VARCHAR(32),
    reservation_key VARCHAR(66),
    tx_hash VARCHAR(80),
    block_number BIGINT,
    error TEXT,
    reason TEXT,
    nonce BIGINT,
    expires_at BIGINT,
    payload_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
