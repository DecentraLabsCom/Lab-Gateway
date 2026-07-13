local _M = {}

local token_revocation_reporter = require "modules.token_revocation_reporter"

local DEFAULT_TOKEN_SECURITY_RETENTION_SECONDS = 1200
local DEFAULT_MAPPING_TTL_SECONDS = 7200

local function header_value(headers, name)
    if not headers then
        return nil
    end
    return headers[name] or headers[string.lower(name)]
end

local function is_json_response(response)
    local content_type = header_value(response.header, "Content-Type")
    return content_type and content_type:match("application/json")
end

local function clear_mappings(dict, username, token)
    if username and username ~= "" then
        dict:delete("token:" .. username)
    end
    if token and token ~= "" then
        dict:delete("guac_token:" .. token)
        dict:delete("guac_jwt_exp:" .. token)
        dict:delete("guac_jwt_last_seen:" .. token)
        dict:delete("guac_jti:" .. token)
        dict:delete("guac_reservation:" .. token)
    end
end

local function security_error(cjson)
    return {
        status = 503,
        body = cjson.encode({
            message = "Institutional session could not be secured",
            type = "SECURITY_ERROR",
        }) or '{"message":"Institutional session could not be secured","type":"SECURITY_ERROR"}',
        header = { ["Content-Type"] = "application/json" },
    }
end

local function set_mapping(ngx, dict, key, value, ttl)
    if value == nil or value == "" then
        ngx.log(ngx.ERR, "Guacamole token - Missing security mapping " .. key)
        return false
    end
    local ok, err = dict:set(key, value, ttl)
    if not ok then
        ngx.log(ngx.ERR, "Guacamole token - Unable to store security mapping " .. key .. ": " .. tostring(err))
        return false
    end
    return true
end

local function store_manual_mappings(ngx, dict, username, token)
    if not set_mapping(ngx, dict, "token:" .. username, token, DEFAULT_MAPPING_TTL_SECONDS) then
        return false
    end
    if not set_mapping(ngx, dict, "guac_token:" .. token, username, DEFAULT_MAPPING_TTL_SECONDS) then
        clear_mappings(dict, username, token)
        return false
    end
    return true
end

local function secure_reservation_token(ngx, dict, username, token, cjson, deps)
    local jwt_exp = tonumber(ngx.ctx.jwt_exp) or tonumber(dict:get("exp:" .. username))
    local jwt_jti = ngx.ctx.jwt_jti
    local reservation_key = ngx.ctx.jwt_reservation_key
    if not jwt_exp or not jwt_jti or jwt_jti == "" or not reservation_key or reservation_key == "" then
        ngx.log(ngx.ERR, "Guacamole token - Incomplete JWT security context")
        clear_mappings(dict, username, token)
        return security_error(cjson)
    end

    local retention = tonumber(ngx.shared.config:get("guac_token_security_retention_seconds"))
        or DEFAULT_TOKEN_SECURITY_RETENTION_SECONDS
    local mapping_ttl = math.max(1, jwt_exp - ngx.time() + math.max(1, retention))
    local mappings = {
        { "token:" .. username, token },
        { "guac_token:" .. token, username },
        { "guac_jwt_exp:" .. token, jwt_exp },
        { "guac_jwt_last_seen:" .. token, ngx.time() },
        { "guac_jti:" .. token, jwt_jti },
        { "guac_reservation:" .. token, reservation_key },
    }
    for _, mapping in ipairs(mappings) do
        if not set_mapping(ngx, dict, mapping[1], mapping[2], mapping_ttl) then
            clear_mappings(dict, username, token)
            return security_error(cjson)
        end
    end

    local reporter = (deps and deps.revocation_reporter) or token_revocation_reporter
    local ok, registered, err = pcall(reporter.register, ngx, {
        authToken = token,
        username = username,
        reservationKey = reservation_key,
        jwtJti = jwt_jti,
        gatewayId = ngx.shared.config:get("server_name"),
        expiresAt = jwt_exp,
    }, deps and deps.revocation_delivery)
    if not ok or not registered then
        ngx.log(ngx.ERR, "Guacamole token - Durable revocation registration failed: " .. tostring(err or registered))
        clear_mappings(dict, username, token)
        return security_error(cjson)
    end

    ngx.log(ngx.INFO, "Guacamole token - JWT-backed session secured for " .. username)
    return nil
end

function _M.handle_response(ngx_ctx, response, deps)
    local ngx = ngx_ctx or ngx
    local cjson = (deps and deps.cjson) or require "cjson.safe"
    if not response or response.status ~= 200 or not is_json_response(response) then
        return response
    end

    local decoded = cjson.decode(response.body or "")
    if not decoded or not decoded.authToken or not decoded.username then
        return response
    end

    local token = tostring(decoded.authToken)
    local username = string.lower(tostring(decoded.username))
    local dict = ngx.shared.cache

    if ngx.ctx and ngx.ctx.jwt_authenticated then
        local failed = secure_reservation_token(ngx, dict, username, token, cjson, deps)
        if failed then
            return failed
        end
    else
        store_manual_mappings(ngx, dict, username, token)
    end

    return response
end

return _M
