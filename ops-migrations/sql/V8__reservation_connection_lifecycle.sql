-- Durable connection state and reconnect grace for reservation lifecycle actions.

CREATE TABLE IF NOT EXISTS reservation_session_lifecycle (
    reservation_id VARCHAR(128) NOT NULL,
    lab_id VARCHAR(128) NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    disconnected_at DATETIME NULL,
    cycle_id VARCHAR(32) NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (reservation_id),
    KEY idx_reservation_session_state (state, disconnected_at)
);

CREATE TABLE IF NOT EXISTS reservation_session_connections (
    reservation_id VARCHAR(128) NOT NULL,
    lab_id VARCHAR(128) NOT NULL,
    source VARCHAR(16) NOT NULL,
    connection_id VARCHAR(128) NOT NULL,
    state VARCHAR(16) NOT NULL,
    sequence INT NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    cycle_id VARCHAR(32) NULL,
    connected_at DATETIME NULL,
    disconnected_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (reservation_id, source, connection_id),
    KEY idx_reservation_session_connections (reservation_id, state),
    KEY idx_reservation_session_disconnected (state, disconnected_at)
);
