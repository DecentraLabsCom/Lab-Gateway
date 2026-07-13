local _M = {}
local demo_guard = require "modules.demo_guard"

local function is_websocket_tunnel(uri)
    return uri and uri:match("/guacamole/websocket%-tunnel")
end

local function reject(ngx, message)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message)
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local function enforce_guac_timeout(ngx, dict)
    local token = ngx.var.arg_token
    if not token or token == "" then return false end
    local exp = tonumber(dict:get("guac_jwt_exp:" .. token))
    if not exp then
        local username = dict:get("guac_token:" .. token)
        if username and tostring(username):match("^dlabs%-res%-") then
            reject(ngx, "Unauthorized: Guacamole access session is no longer valid")
            return true
        end
        return false
    end
    local now = ngx.time()
    if now >= exp then
        reject(ngx, "Unauthorized: Guacamole JWT session expired")
        return true
    end
    local idle = tonumber(ngx.shared.config:get("jwt_guac_idle_timeout_seconds")) or 60
    local last = tonumber(dict:get("guac_jwt_last_seen:" .. token))
    if last and now - last > idle then
        reject(ngx, "Unauthorized: Guacamole JWT session expired")
        return true
    end
    local retention = tonumber(ngx.shared.config:get("guac_token_security_retention_seconds")) or 1200
    dict:set("guac_jwt_last_seen:" .. token, now, math.max(1, exp - now + math.max(1, retention)))
    return false
end

local function observe_reservation_websocket(ngx, deps)
    if not ngx.ctx.jwt_authenticated or not is_websocket_tunnel(ngx.var.uri) then
        return true
    end

    local reporter = (deps and deps.access_audit_reporter) or require "modules.access_audit_reporter"
    local ok, persisted, err = pcall(
        reporter.report_guacamole_session_observed,
        ngx,
        deps and deps.access_audit
    )
    if ok and persisted then
        return true
    end

    ngx.log(ngx.ERR, "Access audit - refusing websocket without durable observation: " .. tostring(err or persisted))
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE or 503
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Session observation unavailable")
    ngx.exit(ngx.status)
    return false
end

function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache
    -- Guacamole's header authentication extension must only ever receive a
    -- username selected by this trusted gateway. Never forward a client value.
    ngx.req.clear_header("Authorization")
    if enforce_guac_timeout(ngx, dict) then return end

    local cookies = ngx.var.http_cookie
    if not cookies or cookies == "" then return end
    local jti = string.match(cookies, "JTI=([^;]+)")
    if not jti or jti == "" then return end
    local username = dict:get("username:" .. jti)
    local exp = username and tonumber(dict:get("exp:" .. username))
    if not username or not exp then return end
    if ngx.time() >= exp then
        reject(ngx, "Unauthorized: access session expired")
        return
    end
    ngx.req.set_header("Authorization", username)
    ngx.ctx.jwt_authenticated = true
    ngx.ctx.jwt_username = username
    ngx.ctx.jwt_jti = jti
    ngx.ctx.jwt_reservation_key = dict:get("reservation:" .. jti)
    ngx.ctx.jwt_exp = exp
    demo_guard.run(ngx)
    return observe_reservation_websocket(ngx, deps)
end

return _M
