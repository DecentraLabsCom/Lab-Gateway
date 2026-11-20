-- Per-station automatic reservation-end and weekly Shutdown Ops settings.

CREATE TABLE IF NOT EXISTS shutdown_ops_schedules (
    host VARCHAR(128) NOT NULL,
    after_reservation_end BOOLEAN NOT NULL DEFAULT FALSE,
    weekly_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    day_of_week TINYINT NOT NULL DEFAULT 6,
    hour TINYINT NOT NULL DEFAULT 23,
    minute TINYINT NOT NULL DEFAULT 0,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Madrid',
    last_scheduled_at DATETIME NULL,
    last_started_at DATETIME NULL,
    last_finished_at DATETIME NULL,
    last_status VARCHAR(32) NULL,
    last_message VARCHAR(1024) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (host),
    KEY idx_shutdown_ops_due (weekly_enabled, last_scheduled_at)
);
