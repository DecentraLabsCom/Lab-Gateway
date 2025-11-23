-- Lab Station ops persistence (heartbeats, events, host catalog)

CREATE TABLE IF NOT EXISTS lab_hosts (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    address VARCHAR(255) NOT NULL,
    mac VARCHAR(32),
    mode ENUM('pure','hybrid') DEFAULT 'pure',
    last_seen DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_lab_hosts_name (name)
);

CREATE TABLE IF NOT EXISTS lab_host_heartbeat (
    id BIGINT NOT NULL AUTO_INCREMENT,
    host_id BIGINT NOT NULL,
    timestamp_utc DATETIME NOT NULL,
    ready BOOLEAN,
    local_mode BOOLEAN,
    local_session BOOLEAN,
    last_forced_logoff_ts DATETIME NULL,
    last_forced_logoff_user VARCHAR(128),
    last_power_action_ts DATETIME NULL,
    last_power_action_mode VARCHAR(32),
    raw_json LONGTEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_host_ts (host_id, timestamp_utc),
    CONSTRAINT fk_heartbeat_host FOREIGN KEY (host_id) REFERENCES lab_hosts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lab_host_events (
    id BIGINT NOT NULL AUTO_INCREMENT,
    host_id BIGINT NOT NULL,
    kind VARCHAR(64) NOT NULL,
    timestamp_utc DATETIME NOT NULL,
    payload JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_host_kind_ts (host_id, kind, timestamp_utc),
    CONSTRAINT fk_events_host FOREIGN KEY (host_id) REFERENCES lab_hosts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservation_operations (
    id BIGINT NOT NULL AUTO_INCREMENT,
    reservation_id VARCHAR(128) NOT NULL,
    lab_id VARCHAR(128),
    host VARCHAR(128) NOT NULL,
    action VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    response_code INT,
    duration_ms INT,
    payload JSON,
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_reservation_action (reservation_id, action)
);
