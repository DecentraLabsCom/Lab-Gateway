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
    ngx.log(ngx.WARN, "LAB_MANAGER_TOKEN not set; /ops endpoints will remain disabled and /lab-manager will be loopback-only")
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
    -- The runner is an optional profile.  An empty value must keep a plain
    -- `docker compose up` deployment coherent (no runner container).
    fmu_runner_enabled = false
else
    fmu_runner_enabled = not (fmu_runner_env == "0" or fmu_runner_env == "false" or fmu_runner_env == "no")
end

local jwt_guac_idle_timeout_seconds = tonumber(trim(os.getenv("JWT_GUAC_IDLE_TIMEOUT_SECONDS")) or "") or 60
if jwt_guac_idle_timeout_seconds < 1 then
    jwt_guac_idle_timeout_seconds = 60
end
local api_session_timeout_minutes = tonumber(trim(os.getenv("API_SESSION_TIMEOUT")) or "") or 15
if api_session_timeout_minutes < 1 then
    api_session_timeout_minutes = 15
end
local guac_token_security_retention_seconds = api_session_timeout_minutes * 60 + 300

config:set("server_name", server_name)
config:set("guac_uri", "/guacamole")
config:set("issuer", issuer)
config:set("lite_mode", lite_mode and 1 or 0)
config:set("fmu_runner_enabled", fmu_runner_enabled and 1 or 0)
config:set("admin_user", admin_user)
config:set("admin_pass", admin_pass)
config:set("https_port", https_port)
config:set("auto_logout_on_disconnect", auto_logout:lower() == "true")
config:set("jwt_guac_idle_timeout_seconds", jwt_guac_idle_timeout_seconds)
config:set("guac_token_security_retention_seconds", guac_token_security_retention_seconds)
if guac_api_url and guac_api_url ~= "" then
    config:set("guac_api_url", guac_api_url)
else
    config:set("guac_api_url", default_guac_api_url)
end

-- AAS server base URL for /aas/* proxy.
-- Empty → use bundled BaSyx (http://basyx-aas-server:8081) when --profile aas is active.
-- Non-empty → proxy to the configured external AAS server URL.
local basyx_aas_raw = trim(os.getenv("BASYX_AAS_URL")) or ""
local basyx_aas_url = ((basyx_aas_raw ~= "") and basyx_aas_raw or "http://basyx-aas-server:8081"):gsub("/+$", "")  -- strip trailing slash
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

-- Demo access configuration
local demo_user = trim(os.getenv("DEMO_USER")) or ""
if demo_user == "" then demo_user = "demo" end
config:set("demo_user", demo_user)
local demo_lab_id = trim(os.getenv("DEMO_LAB_ID")) or ""
config:set("demo_lab_id", demo_lab_id)
local marketplace_url = (trim(os.getenv("MARKETPLACE_URL")) or ""):gsub("/+$", "")
config:set("marketplace_url", marketplace_url)

if fmu_runner_enabled then
    ngx.log(ngx.INFO, "FMU runner integration enabled")
else
    ngx.log(ngx.INFO, "FMU runner integration disabled: /fmu and FMU AAS sync endpoints will return 503")
end

-- Read exactly one mode-specific public-key source.  Falling back across
-- these paths is unsafe: a stale local Full key must never be accepted by a
-- Lite gateway, and a downloaded remote key must never override Full mode.
local active_key_path
if lite_mode then
    active_key_path = "/etc/ssl/private/public_key.pem"
else
    active_key_path = "/etc/openresty/jwt-keys/public_key.pem"
end
local previous_key_path
if lite_mode then
    previous_key_path = "/etc/ssl/private/previous_public_key.pem"
else
    -- The backend key mount is read-only; the overlap copy is maintained by
    -- init-ssl.sh in the writable cert volume for both deployment modes.
    previous_key_path = "/etc/ssl/private/previous_public_key.pem"
end
local key_paths = { active_key_path, previous_key_path }
config:set("jwt_public_key_path", active_key_path)
config:set("jwt_previous_public_key_path", previous_key_path)
config:set("jwt_public_key_mode", lite_mode and "remote" or "local")
local public_key_loaded = false
local previous_key_loaded = false
for index, path in ipairs(key_paths) do
    local file = io.open(path, "r")
    if file then
        local public_key = file:read("*all")
        file:close()
        if public_key and public_key ~= "" then
            local cache_key = index == 1 and "public_key" or "public_key_previous"
            ngx.shared.cache:set(cache_key, public_key)
            if index == 1 then
                public_key_loaded = true
                ngx.log(ngx.INFO, "Loaded active JWT public key from: " .. path)
            else
                previous_key_loaded = true
                ngx.log(ngx.INFO, "Loaded previous JWT public key for rotation overlap from: " .. path)
            end
        end
    end
end
if not public_key_loaded then
    ngx.shared.cache:delete("public_key")
end
if not previous_key_loaded then
    ngx.shared.cache:delete("public_key_previous")
end
if not public_key_loaded then
    ---@diagnostic disable-next-line: param-type-mismatch
    ngx.log(ngx.ERR, "Unable to read active JWT public key file: " .. active_key_path)
end
