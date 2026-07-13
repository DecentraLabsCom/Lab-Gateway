local _M = {}
local token_revocation_reporter = require "modules.token_revocation_reporter"
local DEFAULT_TOKEN_SECURITY_RETENTION_SECONDS = 1200
local DEFAULT_MAPPING_TTL_SECONDS = 7200

local function is_json_response(content_type)
    return content_type and content_type:match("application/json")
end

local function is_json_body(body)
    return body and body ~= "" and body:match("^%s*[{%[]")
end

local function fail_closed(ngx, cjson, dict, username_lower, token)
    dict:delete("token:" .. username_lower)
    dict:delete("guac_token:" .. token)
    dict:delete("guac_jwt_exp:" .. token)
    dict:delete("guac_jwt_last_seen:" .. token)
    dict:delete("guac_jti:" .. token)
    dict:delete("guac_reservation:" .. token)
    ngx.header["Content-Length"] = nil
    return cjson.encode({
        message = "Institutional session could not be secured",
        type = "SECURITY_ERROR",
    })
end

function _M.run(ngx_ctx, chunk, eof, deps)
    local ngx = ngx_ctx or ngx
    local cjson = (deps and deps.cjson) or require "cjson"

    ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")

    if not eof then
        return ""
    end

    local body = ngx.ctx.response_body

    local content_type = ngx.header["Content-Type"]
    if not is_json_response(content_type) then
        ngx.log(ngx.DEBUG, "Body filter - Skipping non-JSON response (Content-Type: " .. tostring(content_type) .. ")")
        return body
    end

    if not is_json_body(body) then
        ngx.log(ngx.WARN, "Body filter - Response is not JSON format. Body preview: " .. tostring(body and body:sub(1, 200)))
        return body
    end

    local success, decoded = pcall(cjson.decode, body)
    if not success then
        ngx.log(ngx.ERR, "Body filter - JSON decode error: " .. tostring(decoded))
        return body
    end

    if not (decoded and decoded.authToken and decoded.username) then
        ngx.log(ngx.DEBUG, "Body filter - No authToken/username in response, skipping.")
        return body
    end

    local dict = ngx.shared.cache
    local username_lower = string.lower(decoded.username)
    local jwt_exp = nil
    if ngx.ctx and ngx.ctx.jwt_authenticated then
        jwt_exp = tonumber(ngx.ctx.jwt_exp) or tonumber(dict:get("exp:" .. username_lower))
    end
    local mapping_ttl = DEFAULT_MAPPING_TTL_SECONDS
    if jwt_exp then
        local retention = tonumber(ngx.shared.config:get("guac_token_security_retention_seconds"))
            or DEFAULT_TOKEN_SECURITY_RETENTION_SECONDS
        mapping_ttl = math.max(1, jwt_exp - ngx.time() + math.max(1, retention))
    end

    local ok, err = dict:set("token:" .. username_lower, decoded.authToken, mapping_ttl)
    if not ok then
        ngx.log(ngx.ERR, "Body filter - Error storing token in shared dict: " .. tostring(err))
        if ngx.ctx and ngx.ctx.jwt_authenticated then
            return fail_closed(ngx, cjson, dict, username_lower, decoded.authToken)
        end
        return body
    end

    local ok_reverse, err_reverse = dict:set("guac_token:" .. decoded.authToken, username_lower, mapping_ttl)
    if not ok_reverse then
        ngx.log(ngx.ERR, "Body filter - Error storing reverse token mapping: " .. tostring(err_reverse))
        if ngx.ctx and ngx.ctx.jwt_authenticated then
            return fail_closed(ngx, cjson, dict, username_lower, decoded.authToken)
        end
        return body
    end

    if ngx.ctx and ngx.ctx.jwt_authenticated then
        if jwt_exp then
            dict:set("guac_jwt_exp:" .. decoded.authToken, jwt_exp, mapping_ttl)
            dict:set("guac_jwt_last_seen:" .. decoded.authToken, ngx.time(), mapping_ttl)
            if ngx.ctx.jwt_jti then
                dict:set("guac_jti:" .. decoded.authToken, ngx.ctx.jwt_jti, mapping_ttl)
            end
            if ngx.ctx.jwt_reservation_key then
                dict:set("guac_reservation:" .. decoded.authToken, ngx.ctx.jwt_reservation_key, mapping_ttl)
            end
            local registered = token_revocation_reporter.schedule(ngx, {
                authToken = decoded.authToken,
                username = username_lower,
                reservationKey = ngx.ctx.jwt_reservation_key,
                jwtJti = ngx.ctx.jwt_jti,
                gatewayId = ngx.shared.config:get("server_name"),
                expiresAt = jwt_exp,
            }, deps and deps.revocation_reporter)
            if not registered then
                return fail_closed(ngx, cjson, dict, username_lower, decoded.authToken)
            end
            ngx.log(ngx.INFO, "Body filter - JWT-backed session token marked for " .. decoded.username)
        end
    end

    ngx.log(ngx.INFO, "Body filter - Session token stored for " .. decoded.username)
    return body
end

return _M
