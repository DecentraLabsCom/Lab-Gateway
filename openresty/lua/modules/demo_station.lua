-- Physical Lab Station lifecycle for anonymous demo sessions.
--
-- Demo operations use the local Ops Worker but never masquerade as an
-- on-chain reservation.  The worker records the operational id demo:<jti>
-- in its local timeline and performs the synchronous prepare/release steps.

local ok_http, resty_http = pcall(require, "resty.http")
local cjson = require "cjson.safe"

local _M = {}

local DEFAULT_OPS_API = "http://ops-worker:8081"
local DEFAULT_TIMEOUT_SECONDS = 15
local DEFAULT_RETENTION_SECONDS = 1200
local OPERATION_PREFIX = "demo_operation:"
local CLEANUP_PENDING_PREFIX = "demo_cleanup_pending:"
local ENDED_PREFIX = "demo_ended:"

local function trim(value)
    if value == nil then return "" end
    return (tostring(value):gsub("^%s*(.-)%s*$", "%1"))
end

local function config_value(ngx, key)
    local config = ngx.shared and ngx.shared.config
    if config and config.get then
        return config:get(key)
    end
    return nil
end

local function canonical_lab_id(value)
    local normalized = trim(value)
    if not normalized:match("^%d+$") then return nil end
    normalized = normalized:gsub("^0+", "")
    return normalized == "" and "0" or normalized
end

local function valid_jti(jti)
    return type(jti) == "string"
        and jti ~= ""
        and #jti <= 128
        and jti:match("^[A-Za-z0-9_.%-]+$") ~= nil
end

local function operation_id(jti)
    return "demo:" .. jti
end

local function retention_seconds(ngx)
    return tonumber(config_value(ngx, "guac_token_security_retention_seconds"))
        or DEFAULT_RETENTION_SECONDS
end

local function request(ngx, path, payload, deps)
    if deps and deps.request then
        return deps.request(path, payload)
    end
    if not ok_http or not resty_http then
        return false, "Ops HTTP client unavailable"
    end

    local token = os.getenv("OPS_INTERNAL_AUTH_TOKEN") or ""
    local header = os.getenv("OPS_INTERNAL_AUTH_HEADER") or "X-Ops-Internal-Token"
    if token == "" then
        return false, "Ops internal authentication is not configured"
    end

    local base = trim(config_value(ngx, "ops_api_url"))
    if base == "" then
        base = trim(os.getenv("OPS_API_URL"))
    end
    if base == "" then base = DEFAULT_OPS_API end
    base = base:gsub("/+$", "")

    local timeout = tonumber(config_value(ngx, "demo_station_timeout_seconds"))
        or DEFAULT_TIMEOUT_SECONDS
    local httpc = resty_http.new()
    httpc:set_timeout(math.max(1, math.floor(timeout * 1000)))
    local response, err = httpc:request_uri(base .. path, {
        method = "POST",
        body = cjson.encode(payload),
        headers = {
            ["Content-Type"] = "application/json",
            [header] = token,
        },
    })
    if not response then
        return false, err or "Ops Worker did not respond"
    end
    local body = cjson.decode(response.body or "") or {}
    if response.status < 200 or response.status >= 300 or body.success ~= true then
        return false, body.error or ("Ops Worker returned HTTP " .. tostring(response.status))
    end
    httpc:set_keepalive(10000, 5)
    return true, body
end

local function operation_lab_id(ngx, jti)
    local dict = ngx.shared and ngx.shared.cache
    return dict and canonical_lab_id(dict:get(OPERATION_PREFIX .. jti))
end

function _M.start(ngx_ctx, jti, exp, deps)
    local ngx = ngx_ctx or ngx
    if not valid_jti(jti) then
        return false, "invalid demo session identifier"
    end
    local lab_id = canonical_lab_id(config_value(ngx, "demo_lab_id"))
    local expires_at = tonumber(exp)
    local dict = ngx.shared and ngx.shared.cache
    if not lab_id or not expires_at or not dict then
        return false, "demo Station lifecycle is not configured"
    end

    if dict:get(ENDED_PREFIX .. jti) then
        return false, "demo session has already ended"
    end
    if dict:get(OPERATION_PREFIX .. jti) then
        return true, { alreadyStarted = true, operationId = operation_id(jti) }
    end

    local ttl = math.max(1, expires_at - ngx.time() + retention_seconds(ngx))
    local stored, store_err = dict:set(OPERATION_PREFIX .. jti, lab_id, ttl)
    if not stored then
        return false, store_err or "unable to persist demo lifecycle state"
    end

    local ok, response = request(ngx, "/api/demo/start", {
        demoId = operation_id(jti),
        labId = lab_id,
        expiresAt = expires_at,
        wake = true,
    }, deps)
    if not ok then
        -- The worker also attempts cleanup for partial starts; this second
        -- idempotent request covers a timeout or a response lost at the edge.
        _M.finish(ngx, jti, "failed", deps)
        return false, response
    end
    return true, response
end

function _M.connected(ngx_ctx, jti, deps)
    local ngx = ngx_ctx or ngx
    if not valid_jti(jti) then return false, "invalid demo session identifier" end
    local lab_id = operation_lab_id(ngx, jti)
    if not lab_id then return false, "demo Station lifecycle is not active" end
    return request(ngx, "/api/demo/event", {
        demoId = operation_id(jti),
        labId = lab_id,
        event = "connected",
    }, deps)
end

function _M.finish(ngx_ctx, jti, reason, deps)
    local ngx = ngx_ctx or ngx
    if not valid_jti(jti) then return false, "invalid demo session identifier" end
    local dict = ngx.shared and ngx.shared.cache
    if not dict then return false, "demo lifecycle storage is unavailable" end
    if dict:get(ENDED_PREFIX .. jti) then return true end

    local lab_id = operation_lab_id(ngx, jti)
    if not lab_id then
        dict:delete(CLEANUP_PENDING_PREFIX .. jti)
        return true
    end
    local normalized_reason = trim(reason):lower()
    if normalized_reason ~= "expired"
        and normalized_reason ~= "failed"
        and normalized_reason ~= "disconnected" then
        normalized_reason = "disconnected"
    end

    local ok, response = request(ngx, "/api/demo/end", {
        demoId = operation_id(jti),
        labId = lab_id,
        reason = normalized_reason,
    }, deps)
    if not ok then
        -- Keep a short-lived retry marker so SessionGuard can retry a failed
        -- close promptly instead of waiting for the demo JWT to expire.
        dict:set(CLEANUP_PENDING_PREFIX .. jti, normalized_reason, math.max(1, retention_seconds(ngx)))
        return false, response
    end

    local ttl = math.max(1, retention_seconds(ngx))
    dict:set(ENDED_PREFIX .. jti, normalized_reason, ttl)
    dict:delete(CLEANUP_PENDING_PREFIX .. jti)
    dict:delete(OPERATION_PREFIX .. jti)
    return true, response
end

return _M
