-- ============================================================================
-- demo_guard.lua - Demo-user access guard
-- ============================================================================
-- The demo restriction is a session policy, not a request counter.  A valid
-- lab-access JTI is registered once in the shared dict and subsequent asset /
-- API requests for that same JTI are pass-throughs.  The entry is removed on
-- the WebSocket tunnel close (with JWT expiry as the hard fallback).
--
-- Availability is fail-closed: a missing configuration, timeout, non-200
-- response, malformed JSON, or non-boolean isAvailable result cannot grant
-- demo access while the booking authority is unknown.

local _M = {}

local DEMO_SESSION_TTL = 600 -- seconds; JWT exp remains the hard upper bound
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

    local cjson = require "cjson.safe"
    local body, parse_err = cjson.decode(res.body)
    if parse_err or type(body) ~= "table" then
        return nil, "availability authority returned invalid JSON"
    end
    if type(body.isAvailable) ~= "boolean" then
        return nil, "availability authority returned no boolean availability"
    end

    return body.isAvailable == false, nil
end

local function session_ttl(ngx)
    local now = ngx.time()
    local exp = tonumber(ngx.ctx and ngx.ctx.jwt_exp)
    if exp then
        return math.max(1, math.min(DEMO_SESSION_TTL, exp - now))
    end
    return DEMO_SESSION_TTL
end

local function current_jti(ngx)
    local jti = ngx.ctx and ngx.ctx.jwt_jti
    if type(jti) ~= "string" or jti == "" or #jti > 256 then
        return nil
    end
    return jti
end

-- Public entry point.  Returns true for a demo request that may continue,
-- false when the request was rejected (ngx.exit is also called).
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    deps = deps or {}

    local config = ngx.shared.config
    local demo_user = config:get("demo_user") or "demo"
    local username = ngx.req.get_headers()["Authorization"]
    if not username or string.lower(username) ~= string.lower(demo_user) then
        return true
    end

    local jti = current_jti(ngx)
    if not jti then
        ngx.log(ngx.WARN, "demo_guard: demo authentication has no valid JTI")
        return reject(ngx, "Demo access is unavailable")
    end

    local demo_sessions = ngx.shared.demo_sessions
    if not demo_sessions then
        ngx.log(ngx.ERR, "demo_guard: demo_sessions shared dictionary is unavailable")
        return reject(ngx, "Demo access is unavailable")
    end

    local session_key = "session:" .. jti
    if demo_sessions:get(session_key) then
        ngx.ctx.demo_session_jti = jti
        return true
    end

    local marketplace_url = config:get("marketplace_url") or ""
    if marketplace_url == "" then
        ngx.log(ngx.WARN, "demo_guard: MARKETPLACE_URL is not configured")
        return reject(ngx, "Demo availability cannot be verified")
    end

    local busy, check_err = is_lab_busy(
        ngx,
        marketplace_url,
        config:get("demo_lab_id") or "",
        deps
    )
    if check_err then
        ngx.log(ngx.WARN, "demo_guard: " .. check_err)
        return reject(ngx, "Demo availability cannot be verified")
    end
    if busy then
        ngx.log(ngx.WARN, "demo_guard: rejecting demo access - lab reservation is active")
        return reject(ngx, "Lab currently reserved. Please try again later.")
    end

    local ttl = session_ttl(ngx)
    local active, incr_err = demo_sessions:incr(ACTIVE_KEY, 1, 0, ttl)
    if not active then
        ngx.log(ngx.ERR, "demo_guard: failed to increment active session set: " .. tostring(incr_err))
        return reject(ngx, "Demo access is unavailable")
    end
    if active > 1 then
        demo_sessions:incr(ACTIVE_KEY, -1, 0)
        ngx.log(ngx.WARN, "demo_guard: rejecting concurrent demo session")
        return reject(ngx, "A demo session is already in progress. Please try again later.")
    end

    local stored, store_err = demo_sessions:set(session_key, "1", ttl)
    if not stored then
        demo_sessions:incr(ACTIVE_KEY, -1, 0)
        ngx.log(ngx.ERR, "demo_guard: failed to register demo JTI: " .. tostring(store_err))
        return reject(ngx, "Demo access is unavailable")
    end

    ngx.ctx.demo_session_jti = jti
    ngx.log(ngx.INFO, "demo_guard: demo session started")
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
    demo_sessions:incr(ACTIVE_KEY, -1, 0)
    ngx.log(ngx.INFO, "demo_guard: demo session ended")
    return true
end

return _M
