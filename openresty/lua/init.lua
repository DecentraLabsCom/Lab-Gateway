-- ============================================================================
-- init.lua - Initialization Phase (init_by_lua)
-- ============================================================================
-- Runs once when OpenResty starts (before worker processes are forked).
-- Purpose: Load configuration from environment variables and read the public
-- key file for JWT verification. Stores config in ngx.shared.config and the
-- public key in ngx.shared.cache for use by all workers.
-- ============================================================================

local config = ngx.shared.config

-- Read config from environment variables or use default values
local admin_user = os.getenv("GUAC_ADMIN_USER") or "guacadmin"
local admin_pass = os.getenv("GUAC_ADMIN_PASS") or "guacadmin"
local server_name = os.getenv("SERVER_NAME") or "localhost"
local issuer = os.getenv("ISSUER") or "https://sarlab.dia.uned.es/auth"

config:set("server_name", server_name)
config:set("guac_uri", "/guacamole")
config:set("issuer", issuer)
config:set("admin_user", admin_user)
config:set("admin_pass", admin_pass)

-- Read the public key from a file
local file = io.open("/etc/ssl/private/public_key.pem", "r")
if file then
    local public_key = file:read("*all")
    file:close()
    -- Store public key in shared dict
    ngx.shared.cache:set("public_key", public_key)
else
    ngx.log(ngx.ERR, "Unable to read public key file")
end