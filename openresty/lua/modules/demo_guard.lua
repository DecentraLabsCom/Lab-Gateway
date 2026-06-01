-- ============================================================================
-- demo_guard.lua — Demo-user access guard
-- ============================================================================
-- Called from access_handler.run() after the Authorization header has been
-- set.  If the authenticated username equals the configured demo user
-- (env DEMO_USER, default "demo") the module:
--
--   1. Rejects (503) if a reservation is currently active for the lab.
--   2. Rejects (503) if there is already 1 concurrent demo session.
--   3. Otherwise records the session in lua_shared_dict demo_sessions and
--      allows the request to proceed.
--
-- Session TTL in the shared dict mirrors the Guacamole session timeout (600 s
-- = 10 min).  Guacamole itself enforces the hard cut-off; the dict entry is
-- only needed for the concurrency counter and is cleaned up automatically.
-- ============================================================================

local _M = {}

local DEMO_SESSION_TTL = 600  -- seconds (must match Guacamole session timeout)
local MARKETPLACE_CHECK_TIMEOUT_MS = 3000

-- Returns true when a confirmed reservation is active for lab_id right now.
-- Calls the Marketplace public endpoint /api/contract/reservation/checkAvailable
-- with a 60-second window starting at the current epoch second.
-- On network error the function returns false (fail-open) and logs a warning
-- so a temporary Marketplace outage does not block demo access permanently.
local function is_lab_busy(marketplace_url, lab_id)
    if not lab_id or lab_id == "" then
        ngx.log(ngx.WARN, "demo_guard: DEMO_LAB_ID not configured; skipping busy check")
        return false
    end

    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(MARKETPLACE_CHECK_TIMEOUT_MS)

    local now = ngx.time()
    local url = marketplace_url
        .. "/api/contract/reservation/checkAvailable"
        .. "?labId=" .. ngx.escape_uri(tostring(lab_id))
        .. "&start=" .. tostring(now)
        .. "&end="   .. tostring(now + 60)

    local res, err = httpc:request_uri(url, { method = "GET", ssl_verify = true })
    if err or not res then
        ngx.log(ngx.WARN, "demo_guard: availability check failed: " .. tostring(err))
        return false  -- fail-open
    end

    if res.status ~= 200 then
        ngx.log(ngx.WARN, "demo_guard: availability check returned HTTP " .. res.status)
        return false  -- fail-open
    end

    local cjson = require "cjson.safe"
    local body, parse_err = cjson.decode(res.body)
    if parse_err or not body then
        ngx.log(ngx.WARN, "demo_guard: failed to parse availability response: " .. tostring(parse_err))
        return false
    end

    -- isAvailable == false  →  slot is taken  →  lab is busy
    return body.isAvailable == false
end

-- Public entry point.  ngx_ctx defaults to the global ngx table.
function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx

    local config = ngx.shared.config
    local demo_user = config:get("demo_user") or "demo"

    -- Determine who is making the request (set by access_handler).
    local username = ngx.req.get_headers()["Authorization"]
    if not username then
        return  -- unauthenticated request – not our concern
    end

    if string.lower(username) ~= string.lower(demo_user) then
        return  -- regular user – no extra restrictions
    end

    -- ── Demo user detected ────────────────────────────────────────────────

    local demo_sessions = ngx.shared.demo_sessions
    local lab_id = config:get("demo_lab_id") or ""

    -- 1. Check whether the lab has an active reservation.
    local marketplace_url = config:get("marketplace_url") or ""
    if marketplace_url == "" then
        -- Try to build a fallback from the Marketplace env used by init.lua.
        -- If it is genuinely missing we skip the check (fail-open) and warn.
        ngx.log(ngx.WARN, "demo_guard: marketplace_url not set; skipping busy check")
    else
        if is_lab_busy(marketplace_url, lab_id) then
            ngx.log(ngx.WARN, "demo_guard: rejecting demo access – lab " .. lab_id .. " is currently in use")
            ngx.header["Content-Type"] = "text/plain"
            ngx.status = 503
            ngx.say("Lab currently in use. Please try again later.")
            return ngx.exit(503)
        end
    end

    -- 2. Concurrency limit: at most 1 simultaneous demo session.
    local count = demo_sessions:get("count") or 0
    if count >= 1 then
        ngx.log(ngx.WARN, "demo_guard: rejecting demo access – concurrent demo session limit reached")
        ngx.header["Content-Type"] = "text/plain"
        ngx.status = 503
        ngx.say("A demo session is already in progress. Please try again in a few minutes.")
        return ngx.exit(503)
    end

    -- 3. Register this demo session.
    -- Increment atomically; the TTL keeps the counter from being stranded if
    -- the session terminates without going through our logout handler.
    local new_count, set_err = demo_sessions:incr("count", 1, 0, DEMO_SESSION_TTL)
    if set_err then
        ngx.log(ngx.ERR, "demo_guard: failed to increment demo session counter: " .. tostring(set_err))
        -- Fail-open: do not block the user because of a counter error.
    else
        ngx.log(ngx.INFO, "demo_guard: demo session started (active=" .. tostring(new_count) .. ")")
    end
end

return _M
