-- Persist transport-neutral Station Contract v3 dimensions alongside the raw payload.
ALTER TABLE lab_host_heartbeat
    ADD COLUMN platform VARCHAR(16) NULL,
    ADD COLUMN management_transport VARCHAR(16) NULL,
    ADD COLUMN contract_version VARCHAR(16) NULL,
    ADD COLUMN profile VARCHAR(32) NULL,
    ADD COLUMN normalized_json JSON NULL;
