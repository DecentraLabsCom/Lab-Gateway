-- ============================================================================
-- demo_guard.lua - Demo-user access guard
-- ============================================================================
-- Demo access is deliberately independent from reservation access.  A demo
-- request must carry the gateway-issued DEMO_JTI context; a normal reservation
-- JTI never enters this policy.

local _M = {}

local DEFAULT_DEMO_SESSION_TTL = 600
local MARKETPLACE_CHECK_TIMEOUT_MS = 3000
local ACTIVE_KEY = "active"

local function reject(ngx, message)
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "text/plain"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(message)
    ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    return false
end

local function configured_session_ttl(ngx)
    local config = ngx.shared.config
    local ttl = tonumber(config and config:get("demo_session_ttl_seconds"))
        or DEFAULT_DEMO_SESSION_TTL
    if ttl < 1 then
        return DEFAULT_DEMO_SESSION_TTL
    end
    return math.floor(math.min(DEFAULT_DEMO_SESSION_TTL, ttl))
end

local function session_ttl(ngx, exp)
    local ttl = configured_session_ttl(ngx)
    local expires_at = tonumber(exp)
    if expires_at then
        return math.max(1, math.min(ttl, expires_at - ngx.time()))
    end
    return ttl
end

-- Returns: busy (boolean), error (string|nil).  A nil busy value means the
-- Marketplace authority could not provide a trustworthy answer.
local function is_lab_busy(ngx, marketplace_url, lab_id, deps)
    if not lab_id or lab_id == "" then
        return nil, "DEMO_LAB_ID is not configured"
    end

    local http_factory = (deps and deps.http_factory) or function()
        local resty_http = require "resty.http"
        return resty_http.new()
    end
    local httpc = http_factory()
    httpc:set_timeout(MARKETPLACE_CHECK_TIMEOUT_MS)

    local now = ngx.time()
    local url = marketplace_url
        .. "/api/contract/reservation/checkAvailable"
        .. "?labId=" .. ngx.escape_uri(tostring(lab_id))
        .. "&start=" .. tostring(now)
        .. "&end=" .. tostring(now + 60)

    local res, err = httpc:request_uri(url, { method = "GET", ssl_verify = true })
    if err or not res then
        return nil, "availability authority unavailable"
    end
    if res.status ~= 200 then
        return nil, "availability authority returned a non-success response"
    end

    local cjson = (deps and deps.cjson) or require "cjson.safe"
    local body, parse_err = cjson.decode(res.body or "")
    if parse_err or type(body) ~= "table" then
        return nil, "availability authority returned invalid JSON"
    end
    if type(body.isAvailable) ~= "boolean" then
        return nil, "availability authority returned no boolean availability"
    end

    return body.isAvailable == false, nil
end

function _M.check_availability(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local config = ngx.shared.config
    local marketplace_url = config:get("marketplace_url") or ""
    if marketplace_url == "" then
        return nil, "MARKETPLACE_URL is not configured"
    end
    return is_lab_busy(ngx, marketplace_url, config:get("demo_lab_id") or "", deps)
end

-- Atomically reserve the single demo slot.  The handoff route calls this
-- before it creates DEMO_JTI mappings, so an unavailable lab never receives a
-- browser session cookie.
function _M.start(ngx_ctx, jti, exp, deps)
    local ngx = ngx_ctx or ngx
    if type(jti) ~= "string" or jti == "" or #jti > 256 then
        return nil, "invalid demo session identifier"
    end

    local demo_sessions = ngx.shared.demo_sessions
    if not demo_sessions then
        return nil, "demo session storage is unavailable"
    end

    local busy, check_err = _M.check_availability(ngx, deps)
    if check_err then
        ngx.log(ngx.WARN, "demo_guard: " .. check_err)
        return nil, "Demo availability cannot be verified"
    end
    if busy then
        return nil, "Lab currently reserved. Please try again later."
    end

    local ttl = session_ttl(ngx, exp)
    local active, incr_err = demo_sessions:incr(ACTIVE_KEY, 1, 0, ttl)
    if not active then
        ngx.log(ngx.ERR, "demo_guard: failed to increment active session set: " .. tostring(incr_err))
        return nil, "Demo access is unavailable"
    end
    if active > 1 then
        local remaining = demo_sessions:incr(ACTIVE_KEY, -1, 0)
        if remaining and remaining <= 0 then
            demo_sessions:delete(ACTIVE_KEY)
        end
        return nil, "A demo session is already in progress. Please try again later."
    end

    local stored, store_err = demo_sessions:set("session:" .. jti, "1", ttl)
    if not stored then
        demo_sessions:delete(ACTIVE_KEY)
        ngx.log(ngx.ERR, "demo_guard: failed to register demo JTI: " .. tostring(store_err))
        return nil, "Demo access is unavailable"
    end

    return ttl
end

-- Public entry point.  A normal reservation request is always a pass-through;
-- only access_handler.lua can mark a request as demo_authenticated after it
-- has validated a gateway-issued DEMO_JTI mapping.
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    if not (ngx.ctx and ngx.ctx.demo_authenticated) then
        return true
    end

    local jti = ngx.ctx.demo_jti
    if type(jti) ~= "string" or jti == "" or #jti > 256 then
        ngx.log(ngx.WARN, "demo_guard: demo authentication has no valid DEMO_JTI")
        return reject(ngx, "Demo access is unavailable")
    end

    local demo_sessions = ngx.shared.demo_sessions
    if not demo_sessions or not demo_sessions:get("session:" .. jti) then
        ngx.log(ngx.WARN, "demo_guard: demo session is no longer active")
        return reject(ngx, "Demo session is no longer active")
    end

    ngx.ctx.demo_session_jti = jti
    return true
end

-- Release exactly one registered JTI.  The existence check makes repeated log
-- phase calls harmless and prevents the active count from going negative.
function _M.release(ngx_ctx, jti)
    local ngx = ngx_ctx or ngx
    if type(jti) ~= "string" or jti == "" then
        return false
    end
    local demo_sessions = ngx.shared.demo_sessions
    local session_key = "session:" .. jti
    if not demo_sessions or not demo_sessions:get(session_key) then
        return false
    end
    demo_sessions:delete(session_key)
    local remaining = demo_sessions:incr(ACTIVE_KEY, -1, 0)
    if remaining and remaining <= 0 then
        demo_sessions:delete(ACTIVE_KEY)
    end
    ngx.log(ngx.INFO, "demo_guard: demo session ended")
    return true
end

return _M
