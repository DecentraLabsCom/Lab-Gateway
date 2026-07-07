local _M = {}

local DEFAULT_AUDIT_URL = "http://blockchain-services:8080/access-audit/internal/session-observed"

local function has_text(value)
    return value ~= nil and tostring(value) ~= ""
end

local function extract_arg(args, name)
    if not args or not name then
        return nil
    end
    return args:match("(^|&)" .. name .. "=([^&]+)")
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

local function default_http_factory()
    local resty_http = require "resty.http"
    return resty_http.new()
end

local function default_cjson()
    return require "cjson.safe"
end

local function post_observation(ngx, payload, deps)
    local access_token = (deps and deps.access_token) or os.getenv("ADMIN_ACCESS_TOKEN") or ""
    if access_token == "" then
        ngx.log(ngx.DEBUG, "Access audit - ADMIN_ACCESS_TOKEN missing; session observation skipped")
        return false
    end

    local cjson = (deps and deps.cjson) or default_cjson()
    local http_factory = (deps and deps.http_factory) or default_http_factory
    local httpc = http_factory()
    local url = (deps and deps.audit_url) or os.getenv("ACCESS_AUDIT_URL") or DEFAULT_AUDIT_URL
    local header_name = (deps and deps.access_token_header) or os.getenv("ADMIN_ACCESS_TOKEN_HEADER") or "X-Access-Token"

    local headers = {
        ["Content-Type"] = "application/json"
    }
    headers[header_name] = access_token

    local res, err = httpc:request_uri(url, {
        method = "POST",
        body = cjson.encode(payload),
        headers = headers,
        keepalive_timeout = 2000,
        keepalive_pool = 5
    })

    if not res then
        ngx.log(ngx.WARN, "Access audit - session observation post failed: " .. tostring(err))
        return false
    end
    if tonumber(res.status) < 200 or tonumber(res.status) >= 300 then
        ngx.log(ngx.WARN, "Access audit - session observation rejected with status " .. tostring(res.status))
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

    local once_key = "access_audit_observed:guacamole:" .. session_hash
    if dict:get(once_key) then
        return false
    end
    dict:set(once_key, true, 7200)

    local payload = {
        reservationKey = reservation_key,
        jwtJti = jwt_jti,
        sessionId = "guac:" .. session_hash,
        gatewayId = (deps and deps.gateway_id) or os.getenv("GATEWAY_ID") or ngx.shared.config:get("server_name"),
        accessType = "guacamole",
        observedAt = ngx.time()
    }

    local function send(premature)
        if premature then
            return
        end
        post_observation(ngx, payload, deps)
    end

    if ngx.timer and ngx.timer.at then
        local ok, err = ngx.timer.at(0, send)
        if not ok then
            ngx.log(ngx.WARN, "Access audit - failed to schedule session observation: " .. tostring(err))
            return post_observation(ngx, payload, deps)
        end
        return true
    end

    return post_observation(ngx, payload, deps)
end

return _M
