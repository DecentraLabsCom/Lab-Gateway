-- Record when OpenResty durably validated a Guacamole bearer token.
-- This column belongs to the Gateway-local revocation queue, not the remote
-- blockchain-services control-plane schema.

ALTER TABLE guacamole_token_revocation_queue
    ADD COLUMN IF NOT EXISTS token_validated_at DATETIME NULL AFTER token_ciphertext;
