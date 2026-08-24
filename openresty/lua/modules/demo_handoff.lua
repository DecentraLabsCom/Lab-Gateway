-- Browser handoff for the isolated, anonymous demo session.

local random = require "resty.random"
local hex = require "modules.hex"
local demo_guard = require "modules.demo_guard"
local demo_station = require "modules.demo_station"
local cjson = require "cjson.safe"

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

local function canonical_lab_id(value)
    if type(value) ~= "string" or not value:match("^%d+$") then
        return nil
    end

    local normalized = value:gsub("^0+", "")
    return normalized == "" and "0" or normalized
end

local function new_jti(deps)
    local bytes = deps and deps.random_bytes and deps.random_bytes()
    if not bytes then bytes = random.bytes(32, true) end
    if not bytes then
        return nil
    end
    return hex.encode(bytes)
end

local function local_readiness(ngx, lab_id, connection_id, username, deps)
    if deps and deps.local_readiness then
        return deps.local_readiness(ngx, lab_id, connection_id, username) == true
    end
    if not ngx.location or not ngx.location.capture then
        return false
    end
    local gateway_response = ngx.location.capture("/gateway/health")
    if not gateway_response or gateway_response.status ~= 200 then
        return false
    end
    local gateway_payload = cjson.decode(gateway_response.body or "")
    if type(gateway_payload) ~= "table" or gateway_payload.status ~= "UP" then
        return false
    end
    local response = ngx.location.capture("/__health_ops")
    if not response or response.status ~= 200 then
        return false
    end
    local payload = cjson.decode(response.body or "")
    local demo = type(payload) == "table" and payload.demo or nil
    if type(payload) ~= "table" or payload.status ~= "ok" or type(demo) ~= "table" then
        return false
    end
    local checks = demo.checks or {}
    return demo.status == "ready"
        and tostring(demo.labId or "") == lab_id
        and tostring(demo.connectionId or "") == connection_id
        and checks.connection == true
        and checks.principal == true
        and checks.permission == true
        and checks.physical_host == true
end

function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    deps = deps or {}

    if ngx.req.get_method() ~= "GET" then
        ngx.header["Allow"] = "GET"
        return fail(ngx, 405, "Method not allowed")
    end

    local config = ngx.shared.config
    local demo_user = config:get("demo_user") or "demo-lab-disabled"
    local demo_lab_id = config:get("demo_lab_id") or ""
    local demo_connection_id = config:get("demo_connection_id") or ""
    local configured_lab_id = canonical_lab_id(tostring(demo_lab_id))
    local requested_lab_id = canonical_lab_id(ngx.var.arg_labId or "")
    if not requested_lab_id then
        return fail(ngx, 400, "A valid demo laboratory identifier is required")
    end
    if not configured_lab_id or requested_lab_id ~= configured_lab_id then
        return fail(ngx, configured_lab_id and 404 or 503, "Demo access is unavailable")
    end
    if not valid_demo_user(demo_user)
        or not demo_connection_id:match("^[1-9][0-9]*$") then
        return fail(ngx, 503, "Demo access is not configured")
    end
    if not local_readiness(ngx, configured_lab_id, tostring(demo_connection_id), demo_user, deps) then
        return fail(ngx, 503, "Demo access is not ready")
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

    local station = deps.demo_station or demo_station
    local prepared, prepare_err = station.start(ngx, jti, exp, deps)
    if not prepared then
        ngx.log(ngx.WARN, "demo_handoff: physical preparation failed: " .. tostring(prepare_err))
        station.finish(ngx, jti, "failed", deps)
        guard.release(ngx, jti)
        return fail(ngx, 503, "Demo laboratory preparation failed")
    end

    local cache = ngx.shared.cache
    if not cache then
        guard.release(ngx, jti)
        station.finish(ngx, jti, "failed", deps)
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
        station.finish(ngx, jti, "failed", deps)
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
