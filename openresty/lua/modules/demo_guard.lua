-- ============================================================================
-- demo_guard.lua - Demo-user access guard
-- ============================================================================
-- Demo access is deliberately independent from reservation access.  A demo
-- request must carry the gateway-issued DEMO_JTI context; a normal reservation
-- JTI never enters this policy.

local _M = {}

local DEFAULT_DEMO_SESSION_TTL = 600
local DEFAULT_PENDING_LEASE_SECONDS = 45
local MARKETPLACE_CHECK_TIMEOUT_MS = 3000
local OCCUPIED_KEY = "occupied"
local PENDING_EXP_PREFIX = "demo_pending_exp:"

local function canonical_lab_id(value)
    if type(value) ~= "string" or not value:match("^%d+$") then
        return nil
    end

    local normalized = value:gsub("^0+", "")
    return normalized == "" and "0" or normalized
end

local function decrement_occupied(demo_sessions)
    local remaining = demo_sessions:incr(OCCUPIED_KEY, -1, 0)
    if remaining and remaining < 0 then
        demo_sessions:set(OCCUPIED_KEY, 0)
        return 0
    end
    return remaining
end

local function configured_pending_lease(ngx)
    local config = ngx.shared.config
    local lease = tonumber(config and config:get("demo_pending_lease_seconds"))
        or DEFAULT_PENDING_LEASE_SECONDS
    if lease < 30 then
        return 30
    end
    return math.floor(math.min(60, lease))
end

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

local function pending_ttl(ngx, exp)
    local ttl = configured_pending_lease(ngx)
    local expires_at = tonumber(exp)
    if expires_at then
        return math.max(1, math.min(ttl, expires_at - ngx.time()))
    end
    return ttl
end

-- Returns: busy (boolean), error (string|nil).  A nil busy value means the
-- Marketplace authority could not provide a trustworthy answer.
local function is_lab_busy(ngx, marketplace_url, lab_id, demo_exp, deps)
    local normalized_lab_id = canonical_lab_id(tostring(lab_id or ""))
    if not normalized_lab_id then
        return nil, "DEMO_LAB_ID is not configured"
    end

    local http_factory = (deps and deps.http_factory) or function()
        local resty_http = require "resty.http"
        return resty_http.new()
    end
    local httpc = http_factory()
    httpc:set_timeout(MARKETPLACE_CHECK_TIMEOUT_MS)

    local now = ngx.time()
    local configured_end = now + configured_session_ttl(ngx)
    local end_time = math.min(tonumber(demo_exp) or configured_end, configured_end)
    local start_time = now + 1
    if start_time >= end_time then
        return true, "demo session has no valid availability window"
    end
    local url = marketplace_url
        .. "/api/demo/eligibility"
        .. "?labId=" .. ngx.escape_uri(normalized_lab_id)
        .. "&start=" .. tostring(start_time)
        .. "&end=" .. tostring(end_time)

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
    if body.labId ~= normalized_lab_id
        or body.start ~= tostring(start_time)
        or body["end"] ~= tostring(end_time)
        or type(body.eligible) ~= "boolean" then
        return nil, "eligibility authority returned invalid JSON"
    end

    return body.eligible ~= true, nil
end

function _M.check_availability(ngx_ctx, exp, deps)
    local ngx = ngx_ctx or ngx
    local config = ngx.shared.config
    local marketplace_url = config:get("marketplace_url") or ""
    if marketplace_url == "" then
        return nil, "MARKETPLACE_URL is not configured"
    end
    return is_lab_busy(ngx, marketplace_url, config:get("demo_lab_id") or "", exp, deps)
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

    local session_key = "session:" .. jti
    local existing_state = demo_sessions:get(session_key)
    if existing_state == "pending" then
        return session_ttl(ngx, exp)
    end
    if existing_state == "active" then
        return session_ttl(ngx, exp)
    end

    local busy, check_err = _M.check_availability(ngx, exp, deps)
    if check_err then
        ngx.log(ngx.WARN, "demo_guard: " .. check_err)
        return nil, "Demo availability cannot be verified"
    end
    if busy then
        return nil, "Lab currently reserved. Please try again later."
    end

    local ttl = pending_ttl(ngx, exp)
    local occupied, incr_err = demo_sessions:incr(OCCUPIED_KEY, 1, 0, ttl)
    if not occupied then
        ngx.log(ngx.ERR, "demo_guard: failed to increment occupied demo slot: " .. tostring(incr_err))
        return nil, "Demo access is unavailable"
    end
    if occupied > 1 then
        decrement_occupied(demo_sessions)
        return nil, "A demo session is already in progress. Please try again later."
    end
    local renewed, renew_err = demo_sessions:set(OCCUPIED_KEY, occupied, ttl)
    if not renewed then
        decrement_occupied(demo_sessions)
        ngx.log(ngx.ERR, "demo_guard: failed to renew occupied demo slot: " .. tostring(renew_err))
        return nil, "Demo access is unavailable"
    end

    local stored, store_err = demo_sessions:set(session_key, "pending", ttl)
    if not stored then
        decrement_occupied(demo_sessions)
        ngx.log(ngx.ERR, "demo_guard: failed to register demo JTI: " .. tostring(store_err))
        return nil, "Demo access is unavailable"
    end

    local cache = ngx.shared.cache
    local pending_exp = ngx.time() + ttl
    local cache_stored, cache_err = cache and cache:set(
        PENDING_EXP_PREFIX .. jti,
        pending_exp,
        session_ttl(ngx, exp)
    )
    if not cache_stored then
        demo_sessions:delete(session_key)
        decrement_occupied(demo_sessions)
        ngx.log(ngx.ERR, "demo_guard: failed to register pending lease: " .. tostring(cache_err))
        return nil, "Demo access is unavailable"
    end

    -- The caller uses this return value for the browser/session TTL. The
    -- shorter pending lease is an internal guard and must not shorten the
    -- cookie or the eventual active session.
    return session_ttl(ngx, exp)
end

-- Promote a pending handoff only after Guacamole has issued its token (or an
-- equivalent tunnel observation has been accepted by the caller).
function _M.activate(ngx_ctx, jti, exp)
    local ngx = ngx_ctx or ngx
    if type(jti) ~= "string" or jti == "" then
        return false, "invalid demo session identifier"
    end
    local demo_sessions = ngx.shared.demo_sessions
    local cache = ngx.shared.cache
    if not demo_sessions or not cache then
        return false, "demo session storage is unavailable"
    end

    local session_key = "session:" .. jti
    local state = demo_sessions:get(session_key)
    if state == "active" then
        return true
    end
    if state ~= "pending" then
        return false, "demo handoff is no longer pending"
    end

    local ttl = session_ttl(ngx, exp)
    local stored, store_err = demo_sessions:set(session_key, "active", ttl)
    if not stored then
        return false, store_err or "unable to promote demo session"
    end
    local occupied = tonumber(demo_sessions:get(OCCUPIED_KEY))
    if not occupied or occupied < 1 then
        demo_sessions:set(session_key, "pending", pending_ttl(ngx, exp))
        return false, "occupied demo slot is missing"
    end
    local renewed, renew_err = demo_sessions:set(OCCUPIED_KEY, occupied, ttl)
    if not renewed then
        demo_sessions:set(session_key, "pending", pending_ttl(ngx, exp))
        return false, renew_err or "unable to renew demo slot"
    end
    cache:delete(PENDING_EXP_PREFIX .. jti)
    return true
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
    if type(jti) ~= "string" or jti == "" or #jti > 256 or ngx.ctx.jwt_jti ~= jti then
        ngx.log(ngx.WARN, "demo_guard: demo authentication has no valid DEMO_JTI")
        return reject(ngx, "Demo access is unavailable")
    end

    local demo_sessions = ngx.shared.demo_sessions
    local state = demo_sessions and demo_sessions:get("session:" .. jti)
    if state ~= "pending" and state ~= "active" then
        ngx.log(ngx.WARN, "demo_guard: demo session is no longer active")
        return reject(ngx, "Demo session is no longer active")
    end

    ngx.ctx.demo_session_jti = jti
    return true
end

-- Release exactly one registered JTI. The existence check makes repeated log
-- phase calls harmless and prevents the occupied count from going negative.
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
    decrement_occupied(demo_sessions)
    if ngx.shared.cache then
        ngx.shared.cache:delete(PENDING_EXP_PREFIX .. jti)
    end
    ngx.log(ngx.INFO, "demo_guard: demo session ended")
    return true
end

return _M
