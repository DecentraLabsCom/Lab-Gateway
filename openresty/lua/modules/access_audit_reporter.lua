local _M = {}

local function has_text(value)
    return value ~= nil and tostring(value) ~= ""
end

local function extract_arg(args, name)
    if not args or not name then
        return nil
    end
    for pair in tostring(args):gmatch("[^&]+") do
        local key, value = pair:match("^([^=]+)=?(.*)$")
        if key == name then
            return key, value
        end
    end
    return nil
end

local function to_hex(binary)
    return (binary:gsub(".", function(c)
        return string.format("%02x", string.byte(c))
    end))
end

local function sha256_hex(ngx, value, deps)
    if deps and deps.sha256_hex then
        return deps.sha256_hex(value)
    end
    if not ngx.sha256_bin then
        return nil
    end
    return to_hex(ngx.sha256_bin(value))
end

local function deliver_observation(payload, deps)
    if deps and deps.deliver then
        return deps.deliver(payload)
    end

    local token = os.getenv("SESSION_OBSERVATION_INGEST_TOKEN") or ""
    if token == "" then
        return false, "SESSION_OBSERVATION_INGEST_TOKEN is not configured"
    end
    local http = require "resty.http"
    local cjson = require "cjson.safe"
    local httpc = http.new()
    httpc:set_timeout(1000)
    local res, err = httpc:request_uri(
        os.getenv("OPS_SESSION_OBSERVATION_INGEST_URL") or "http://ops-worker:8081/internal/session-observations",
        {
            method = "POST",
            body = cjson.encode(payload),
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Gateway-Observation-Token"] = token,
            },
        }
    )
    if not res or res.status < 200 or res.status >= 300 then
        return false, err or (res and ("status " .. res.status) or "no response")
    end
    httpc:set_keepalive(10000, 5)
    return true
end

local function schedule_observation(ngx, payload, deps)
    if deps and deps.schedule then
        return deps.schedule(payload)
    end
    local ok, err = ngx.timer.at(0, function(premature)
        if premature then
            return
        end
        local delivered, delivery_err = deliver_observation(payload, deps)
        if not delivered then
            ngx.log(ngx.WARN, "Access audit - observation ingestion failed: " .. tostring(delivery_err))
        end
    end)
    if not ok then
        ngx.log(ngx.WARN, "Access audit - unable to schedule observation ingestion: " .. tostring(err))
        return false
    end
    return true
end

function _M.report_guacamole_session_observed(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache
    local token = select(2, extract_arg(ngx.var.args, "token"))
    if not has_text(token) then
        return false
    end

    local reservation_key = dict:get("guac_reservation:" .. token)
    local jwt_jti = dict:get("guac_jti:" .. token)
    if not has_text(reservation_key) or not has_text(jwt_jti) then
        ngx.log(ngx.DEBUG, "Access audit - missing reservationKey/jwtJti for Guacamole token")
        return false
    end

    local session_hash = sha256_hex(ngx, token, deps)
    if not has_text(session_hash) then
        ngx.log(ngx.WARN, "Access audit - cannot hash Guacamole session token")
        return false
    end

    return schedule_observation(ngx, {
        dedupKey = session_hash,
        reservationKey = reservation_key,
        jwtJti = jwt_jti,
        sessionId = "guac:" .. session_hash,
        gatewayId = (deps and deps.gateway_id) or os.getenv("GATEWAY_ID") or ngx.shared.config:get("server_name"),
        accessType = "guacamole",
        observedAt = ngx.time(),
    }, deps)
end

return _M
