local _M = {}

local function increment(dict, key)
    if dict then
        dict:incr(key, 1, 0)
    end
end

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
    if ngx.sha256_bin then
        return to_hex(ngx.sha256_bin(value))
    end

    local loaded, digest = pcall(require, "resty.openssl.digest")
    if not loaded then
        return nil
    end
    local instance, new_err = digest.new("sha256")
    if not instance then
        ngx.log(ngx.WARN, "Access audit - cannot initialize SHA-256: " .. tostring(new_err))
        return nil
    end
    local updated, update_err = instance:update(value)
    if not updated then
        ngx.log(ngx.WARN, "Access audit - cannot hash session token: " .. tostring(update_err))
        return nil
    end
    local binary, final_err = instance:final()
    if not binary then
        ngx.log(ngx.WARN, "Access audit - cannot finalize session hash: " .. tostring(final_err))
        return nil
    end
    return to_hex(binary)
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
    httpc:set_timeout(1500)
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

    local reported_at = ngx.time()
    local delivered, err = deliver_observation({
        dedupKey = session_hash,
        reservationKey = reservation_key,
        jwtJti = jwt_jti,
        sessionId = "guac:" .. session_hash,
        gatewayId = (deps and deps.gateway_id) or os.getenv("GATEWAY_ID") or ngx.shared.config:get("server_name"),
        accessType = "guacamole",
        observedAt = reported_at,
        reportedAt = reported_at,
    }, deps)
    if delivered then
        increment(dict, "metric:session_observation_ingest_success")
        return true
    end
    increment(dict, "metric:session_observation_ingest_failure")
    ngx.log(ngx.ERR, "Access audit - durable observation ingestion failed: " .. tostring(err))
    return false, err
end

return _M
