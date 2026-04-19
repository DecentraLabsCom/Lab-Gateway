-- ============================================================================
-- init.lua - Initialization Phase (init_by_lua)
-- ============================================================================
-- Runs once when OpenResty starts (before worker processes are forked).
-- Purpose: Load configuration from environment variables and read the public
-- key file for JWT verification. Stores config in ngx.shared.config and the
-- public key in ngx.shared.cache for use by all workers.
-- ============================================================================

local config = ngx.shared.config

local function require_env(name)
    local value = os.getenv(name)
    if not value or value == "" then
        ngx.log(ngx.ERR, "Missing required env var: " .. name)
        error("missing required env var: " .. name)
    end
    return value
end

local function refuse_default_secret(name, value, disallowed)
    local normalized = tostring(value):lower()
    for _, candidate in ipairs(disallowed or {}) do
        if normalized == candidate then
            ngx.log(ngx.ERR, "Refusing to start with default value for " .. name)
            error("refusing default value for " .. name)
        end
    end
end

-- Read config from environment variables
local admin_user = require_env("GUAC_ADMIN_USER")
local admin_pass = require_env("GUAC_ADMIN_PASS")
local server_name = os.getenv("SERVER_NAME") or "localhost"
local https_port = os.getenv("HTTPS_PORT") or "443"
local auto_logout = os.getenv("AUTO_LOGOUT_ON_DISCONNECT") or "false"
local guac_api_url = os.getenv("GUAC_API_URL")
local default_guac_api_url = "http://guacamole:8080/guacamole/api"

refuse_default_secret("GUAC_ADMIN_PASS", admin_pass, { "guacadmin", "changeme", "change_me", "password", "test" })

local lab_manager_token = os.getenv("LAB_MANAGER_TOKEN")
if not lab_manager_token or lab_manager_token == "" then
    ngx.log(ngx.WARN, "LAB_MANAGER_TOKEN not set; /ops endpoints will remain disabled and /lab-manager will be private-network-only")
else
    refuse_default_secret("LAB_MANAGER_TOKEN", lab_manager_token, { "supersecretvalue", "changeme", "change_me", "password", "test" })
end

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

local function build_local_issuer()
    local name = trim(server_name) or "localhost"
    local port_segment = ""
    if https_port and https_port ~= "" and https_port ~= "443" then
        port_segment = ":" .. https_port
    end
    return string.format("https://%s%s%s", name, port_segment, "/auth")
end

local function normalize_issuer(value)
    local normalized = trim(value)
    if not normalized or normalized == "" then
        return ""
    end
    normalized = normalized:gsub("/+$", "")
    return normalized
end

local configured_issuer = trim(os.getenv("ISSUER"))
local local_issuer = build_local_issuer()
local issuer = build_default_issuer()
local lite_mode = false
if configured_issuer and configured_issuer ~= "" then
    lite_mode = normalize_issuer(configured_issuer) ~= normalize_issuer(local_issuer)
end

local fmu_runner_env = (trim(os.getenv("FMU_RUNNER_ENABLED")) or ""):lower()
local fmu_runner_enabled
if fmu_runner_env == "" then
    -- Keep Full behavior unchanged while allowing Lite to run without fmu-runner by default.
    fmu_runner_enabled = not lite_mode
else
    fmu_runner_enabled = not (fmu_runner_env == "0" or fmu_runner_env == "false" or fmu_runner_env == "no")
end

config:set("server_name", server_name)
config:set("guac_uri", "/guacamole")
config:set("issuer", issuer)
config:set("lite_mode", lite_mode and 1 or 0)
config:set("fmu_runner_enabled", fmu_runner_enabled and 1 or 0)
config:set("admin_user", admin_user)
config:set("admin_pass", admin_pass)
config:set("https_port", https_port)
config:set("auto_logout_on_disconnect", auto_logout:lower() == "true")
if guac_api_url and guac_api_url ~= "" then
    config:set("guac_api_url", guac_api_url)
else
    config:set("guac_api_url", default_guac_api_url)
end

-- AAS server base URL for /aas/* proxy.
-- Empty → use bundled BaSyx (http://basyx-aas-server:8081) when --profile aas is active.
-- Non-empty → proxy to the configured external AAS server URL.
local basyx_aas_raw = trim(os.getenv("BASYX_AAS_URL")) or ""
local basyx_aas_url = (basyx_aas_raw ~= "") and basyx_aas_raw or "http://basyx-aas-server:8081"
basyx_aas_url = basyx_aas_url:gsub("/+$", "")  -- strip trailing slash
config:set("basyx_aas_url", basyx_aas_url)

-- AAS enabled flag: explicit AAS_ENABLED env takes precedence; otherwise infer
-- from BASYX_AAS_URL being explicitly set (non-empty), meaning an external or
-- known-active AAS server has been configured.  When using --profile aas with
-- the bundled BaSyx, set AAS_ENABLED=1 in .env.
local aas_enabled_env = (trim(os.getenv("AAS_ENABLED")) or ""):lower()
local aas_enabled
if aas_enabled_env == "1" or aas_enabled_env == "true" or aas_enabled_env == "yes" then
    aas_enabled = true
elseif aas_enabled_env == "0" or aas_enabled_env == "false" or aas_enabled_env == "no" then
    aas_enabled = false
else
    -- Auto-detect: explicit BASYX_AAS_URL means AAS is intentionally configured.
    aas_enabled = basyx_aas_raw ~= ""
end
config:set("aas_enabled", aas_enabled and 1 or 0)

if lite_mode then
    ngx.log(ngx.INFO, "Lite mode enabled: billing/auth/intents endpoints are restricted on this gateway")
else
    ngx.log(ngx.INFO, "Full mode enabled")
end

if fmu_runner_enabled then
    ngx.log(ngx.INFO, "FMU runner integration enabled")
else
    ngx.log(ngx.INFO, "FMU runner integration disabled: /fmu and FMU AAS sync endpoints will return 503")
end

-- Read the public key from a file
local file = io.open("/etc/ssl/private/public_key.pem", "r")
if file then
    local public_key = file:read("*all")
    file:close()
    -- Store public key in shared dict
    ngx.shared.cache:set("public_key", public_key)
else
    ---@diagnostic disable-next-line: param-type-mismatch
    ngx.log(ngx.ERR, "Unable to read public key file")
end
