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

local function enqueue_observation(ngx, payload, deps)
    if deps and deps.outbox_enqueue then
        return deps.outbox_enqueue(payload)
    end

    local mysql = require "resty.mysql"
    local db = mysql:new()
    db:set_timeout(1000)
    local ok, err = db:connect({
        host = os.getenv("MYSQL_HOSTNAME") or os.getenv("MYSQL_HOST") or "mysql",
        port = tonumber(os.getenv("MYSQL_PORT")) or 3306,
        database = os.getenv("BLOCKCHAIN_MYSQL_DATABASE") or "blockchain_services",
        user = os.getenv("MYSQL_USER"),
        password = os.getenv("MYSQL_PASSWORD"),
        charset = "utf8mb4",
        max_packet_size = 1024 * 1024,
    })
    if not ok then
        ngx.log(ngx.WARN, "Access audit - observation outbox unavailable: " .. tostring(err))
        return false
    end

    local quote = function(value)
        return db:quote_sql_str(tostring(value))
    end
    local observed_at = tonumber(payload.observedAt) or ngx.time()
    local sql = string.format([[
        INSERT INTO gateway_session_observation_outbox (
            dedup_key, reservation_key, jwt_jti, session_id, gateway_id,
            access_type, observed_at, status, next_attempt_at
        ) VALUES (%s, %s, %s, %s, %s, %s, FROM_UNIXTIME(%d), 'PENDING', CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE
            status = IF(status = 'SENT', 'SENT', 'PENDING'),
            next_attempt_at = IF(status = 'SENT', next_attempt_at, CURRENT_TIMESTAMP),
            locked_at = IF(status = 'SENT', locked_at, NULL),
            updated_at = CURRENT_TIMESTAMP
    ]],
        quote(payload.dedupKey),
        quote(payload.reservationKey),
        quote(payload.jwtJti),
        quote(payload.sessionId),
        quote(payload.gatewayId),
        quote(payload.accessType),
        observed_at
    )
    local result, query_err = db:query(sql)
    local keepalive_ok, keepalive_err = db:set_keepalive(10000, 5)
    if not keepalive_ok then
        ngx.log(ngx.DEBUG, "Access audit - unable to pool outbox connection: " .. tostring(keepalive_err))
    end
    if not result then
        ngx.log(ngx.WARN, "Access audit - observation outbox insert failed: " .. tostring(query_err))
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

    local payload = {
        dedupKey = session_hash,
        reservationKey = reservation_key,
        jwtJti = jwt_jti,
        sessionId = "guac:" .. session_hash,
        gatewayId = (deps and deps.gateway_id) or os.getenv("GATEWAY_ID") or ngx.shared.config:get("server_name"),
        accessType = "guacamole",
        observedAt = ngx.time()
    }
    return enqueue_observation(ngx, payload, deps)
end

return _M
