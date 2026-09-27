-- Per-Lab Station weekly Wake Ops verification schedule and latest outcome.
CREATE TABLE IF NOT EXISTS wake_ops_schedules (
    host VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    day_of_week TINYINT NOT NULL DEFAULT 6,
    hour TINYINT NOT NULL DEFAULT 8,
    minute TINYINT NOT NULL DEFAULT 0,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Madrid',
    last_scheduled_at DATETIME NULL,
    last_started_at DATETIME NULL,
    last_finished_at DATETIME NULL,
    last_status VARCHAR(32) NULL,
    last_message VARCHAR(1024) NULL,
    last_initial_power_state VARCHAR(16) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (host),
    KEY idx_wake_ops_due (enabled, last_scheduled_at)
);
