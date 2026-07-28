-- Browser handoff for the isolated, anonymous demo session.

local random = require "resty.random"
local hex = require "modules.hex"
local demo_guard = require "modules.demo_guard"

local _M = {}

local DEFAULT_RATE_LIMIT = 10

local function fail(ngx, status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.say(message)
    return ngx.exit(status)
end

local function configured_rate_limit(ngx)
    local config = ngx.shared.config
    local limit = tonumber(config and config:get("demo_rate_limit_per_minute"))
        or DEFAULT_RATE_LIMIT
    if limit < 1 then
        return DEFAULT_RATE_LIMIT
    end
    return math.floor(limit)
end

local function valid_demo_user(username)
    return type(username) == "string"
        and username ~= ""
        and #username <= 128
        and username:match("^[%w_.%-]+$") ~= nil
end

local function new_jti(deps)
    local bytes = deps and deps.random_bytes and deps.random_bytes()
    if not bytes then bytes = random.bytes(32, true) end
    if not bytes then
        return nil
    end
    return hex.encode(bytes)
end

function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    deps = deps or {}

    if ngx.req.get_method() ~= "GET" then
        ngx.header["Allow"] = "GET"
        return fail(ngx, 405, "Method not allowed")
    end

    local config = ngx.shared.config
    local demo_user = config:get("demo_user") or "demo"
    local demo_lab_id = config:get("demo_lab_id") or ""
    local demo_connection_id = config:get("demo_connection_id") or ""
    if not valid_demo_user(demo_user)
        or demo_lab_id == ""
        or not demo_connection_id:match("^[1-9][0-9]*$") then
        return fail(ngx, 503, "Demo access is not configured")
    end

    local rate_dict = ngx.shared.demo_issue_rate
    if not rate_dict then
        return fail(ngx, 503, "Demo access is unavailable")
    end
    local source = ngx.var.remote_addr or "unknown"
    local rate_key = "source:" .. source
    local attempts, rate_err = rate_dict:incr(rate_key, 1, 0, 60)
    if not attempts then
        ngx.log(ngx.ERR, "demo_handoff: failed to update rate limit: " .. tostring(rate_err))
        return fail(ngx, 503, "Demo access is unavailable")
    end
    if attempts > configured_rate_limit(ngx) then
        return fail(ngx, 429, "Too many demo access attempts. Please try again later.")
    end

    local jti = new_jti(deps)
    if not jti then
        return fail(ngx, 503, "Demo access is unavailable")
    end

    local now = ngx.time()
    local ttl = tonumber(config:get("demo_session_ttl_seconds")) or 600
    ttl = math.max(1, math.min(600, math.floor(ttl)))
    local exp = now + ttl
    local guard = deps.guard or demo_guard
    local session_ttl, start_err = guard.start(ngx, jti, exp, deps)
    if not session_ttl then
        local status = start_err and start_err:match("currently reserved") and 503 or 503
        return fail(ngx, status, start_err or "Demo access is unavailable")
    end

    local cache = ngx.shared.cache
    if not cache then
        guard.release(ngx, jti)
        return fail(ngx, 503, "Demo access is unavailable")
    end

    local stored_session, session_err = cache:set("demo_session:" .. jti, demo_user, session_ttl)
    local stored_exp, exp_err = false, nil
    if stored_session then
        stored_exp, exp_err = cache:set("demo_exp:" .. jti, exp, session_ttl)
    end
    if not stored_session or not stored_exp then
        cache:delete("demo_session:" .. jti)
        cache:delete("demo_exp:" .. jti)
        guard.release(ngx, jti)
        ngx.log(ngx.ERR, "demo_handoff: failed to persist session mapping: " .. tostring(session_err or exp_err))
        return fail(ngx, 503, "Demo access is unavailable")
    end

    ngx.header["Set-Cookie"] = "DEMO_JTI=" .. jti
        .. "; Max-Age=" .. session_ttl
        .. "; Path=/guacamole; Secure; HttpOnly; SameSite=Lax"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Referrer-Policy"] = "no-referrer"
    return ngx.redirect("/guacamole/", ngx.HTTP_SEE_OTHER or 303)
end

return _M
