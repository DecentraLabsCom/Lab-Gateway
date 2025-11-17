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
local https_port = os.getenv("HTTPS_PORT") or "443"
local auto_logout = os.getenv("AUTO_LOGOUT_ON_DISCONNECT") or "false"
local guac_api_url = os.getenv("GUAC_API_URL")

local function trim(value)
    if not value then
        return nil
    end
    return (value:gsub("^%s*(.-)%s*$", "%1"))
end

local function build_default_issuer()
    local override = trim(os.getenv("ISSUER"))
    if override and override ~= "" then
        return override
    end

    local name = trim(server_name) or "localhost"
    local port_segment = ""
    if https_port and https_port ~= "" and https_port ~= "443" then
        port_segment = ":" .. https_port
    end

    return string.format("https://%s%s%s", name, port_segment, "/auth")
end

local issuer = build_default_issuer()

config:set("server_name", server_name)
config:set("guac_uri", "/guacamole")
config:set("issuer", issuer)
config:set("admin_user", admin_user)
config:set("admin_pass", admin_pass)
config:set("https_port", https_port)
config:set("auto_logout_on_disconnect", auto_logout:lower() == "true")
if guac_api_url and guac_api_url ~= "" then
    config:set("guac_api_url", guac_api_url)
else
    config:set("guac_api_url", "http://127.0.0.1:8080/guacamole/api")
end

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
