-- Record when OpenResty durably validated a Guacamole bearer token.
-- This column belongs to the Gateway-local revocation queue, not the remote
-- blockchain-services control-plane schema.

SET @token_validated_at_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'guacamole_token_revocation_queue'
      AND column_name = 'token_validated_at'
);

SET @add_token_validated_at = IF(
    @token_validated_at_exists = 0,
    'ALTER TABLE guacamole_token_revocation_queue ADD COLUMN token_validated_at DATETIME NULL AFTER token_ciphertext',
    'SELECT 1'
);

PREPARE add_token_validated_at FROM @add_token_validated_at;
EXECUTE add_token_validated_at;
DEALLOCATE PREPARE add_token_validated_at;
