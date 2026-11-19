local _M = {}
local demo_guard = require "modules.demo_guard"
local reservation_connection_signal = require "modules.reservation_connection_signal"

local function register_reservation_tunnel(ngx, reservation_id, lab_id)
    if ngx.var.uri ~= "/guacamole/websocket-tunnel"
        or string.lower(tostring(ngx.var.http_upgrade or "")) ~= "websocket"
        or not reservation_id or reservation_id == ""
        or not lab_id or lab_id == "" then
        return
    end

    local request_id = tostring(ngx.var.request_id or "")
    if #request_id < 1 or #request_id > 128
        or not request_id:match("^[A-Za-z0-9][A-Za-z0-9_.:-]*$") then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Reservation session is unavailable")
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    local event = {
        reservationId = reservation_id,
        labId = lab_id,
        source = "guacamole",
        connectionId = request_id,
        eventId = request_id .. ":1",
        event = "connected",
        sequence = 1,
    }
    local recorded, result, status = reservation_connection_signal.record(ngx, event)
    if not recorded then
        ngx.log(ngx.WARN, "Reservation tunnel registration failed: ", tostring(result))
        reservation_connection_signal.record(ngx, {
            reservationId = reservation_id,
            labId = lab_id,
            source = "guacamole",
            connectionId = request_id,
            eventId = request_id .. ":2",
            event = "failed",
            sequence = 2,
        })
        local response_status = status == ngx.HTTP_CONFLICT and ngx.HTTP_CONFLICT
            or status == ngx.HTTP_FORBIDDEN and ngx.HTTP_FORBIDDEN
            or ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.status = response_status
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Reservation session is unavailable")
        return ngx.exit(response_status)
    end

    ngx.ctx.reservation_connection = {
        reservationId = reservation_id,
        labId = lab_id,
        source = "guacamole",
        connectionId = request_id,
        eventId = request_id .. ":2",
        event = "disconnected",
        sequence = 2,
    }
end

local function reject(ngx, message)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message)
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local function cookie_value(cookies, name)
    if not cookies then
        return nil
    end
    for pair in tostring(cookies):gmatch("[^;]+") do
        local key, value = pair:match("^%s*([^=;%s]+)%s*=%s*(.-)%s*$")
        if key == name then
            return value
        end
    end
    return nil
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
    local username = dict:get("guac_token:" .. token)
    -- Demo sessions use the same hard expiry queue as reservation sessions,
    -- but they must not be invalidated by the short idle timeout while a
    -- Guacamole WebSocket is quiet.
    if dict:get("guac_demo:" .. token) then
        dict:set("guac_jwt_last_seen:" .. token, now, math.max(1, exp - now))
        return false
    end
    -- Reservation-backed auth tokens are bounded by the lab JWT expiration.
    -- A quiet WebSocket does not emit token-bearing HTTP requests, so the
    -- short idle timeout must not invalidate a still-valid reservation.
    if username and tostring(username):lower():match("^dlabs%-res%-") then
        dict:set("guac_jwt_last_seen:" .. token, now, math.max(1, exp - now))
        return false
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

function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache
    -- Guacamole's header authentication extension must only ever receive a
    -- username selected by this trusted gateway. Never forward a client value.
    ngx.req.clear_header("Authorization")
    if enforce_guac_timeout(ngx, dict) then return end

    local cookies = ngx.var.http_cookie
    if not cookies or cookies == "" then return end

    -- Demo handoff is intentionally a separate cookie and cache namespace.
    -- It cannot satisfy the reservation JTI path and never receives a
    -- reservation key or durable economic-session registration.
    local demo_jti = cookie_value(cookies, "DEMO_JTI")
    if demo_jti and demo_jti ~= "" and dict:get("demo_session:" .. demo_jti) then
        if dict:get("demo_ended:" .. demo_jti) then
            reject(ngx, "Unauthorized: demo access session has ended")
            return
        end
        local demo_username = dict:get("demo_session:" .. demo_jti)
        local demo_exp = tonumber(dict:get("demo_exp:" .. demo_jti))
        if not demo_username or not demo_exp then
            return
        end
        if ngx.time() >= demo_exp then
            reject(ngx, "Unauthorized: demo access session expired")
            return
        end
        ngx.req.set_header("Authorization", demo_username)
        ngx.ctx.demo_authenticated = true
        ngx.ctx.demo_username = demo_username
        ngx.ctx.demo_jti = demo_jti
        ngx.ctx.demo_exp = demo_exp
        ngx.ctx.jwt_jti = demo_jti
        ngx.ctx.jwt_exp = demo_exp
        demo_guard.run(ngx)
        return
    end

    local jti = cookie_value(cookies, "JTI")
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
    ngx.ctx.jwt_lab_id = dict:get("lab:" .. jti)
    ngx.ctx.jwt_exp = exp
    register_reservation_tunnel(
        ngx,
        ngx.ctx.jwt_reservation_key,
        ngx.ctx.jwt_lab_id
    )
end

return _M
