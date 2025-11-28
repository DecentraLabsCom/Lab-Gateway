local _M = {}

---Handles the header filter phase by validating Guacamole JWT responses and
-- issuing a secure cookie that propagates authenticated sessions.
-- @param ngx_ctx table Optional ngx-like context (defaults to global ngx).
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local jwt = (deps and deps.jwt) or require "resty.jwt"
    local dict = ngx.shared.cache

    -- Fix Location header redirects to include correct port
    local status = ngx.status
    if status == 301 or status == 302 or status == 303 or status == 307 or status == 308 then
        local location = ngx.header["Location"]
        if location then
            ngx.log(ngx.INFO, "Header filter - Detected redirect with Location: " .. location)

            local config = ngx.shared.config
            local https_port = config:get("https_port") or "443"
            local server_name = config:get("server_name") or "localhost"

            if location:sub(1, 1) == "/" then
                local new_location = "https://" .. server_name
                if https_port ~= "443" then
                    new_location = new_location .. ":" .. https_port
                end
                new_location = new_location .. location
                ngx.header["Location"] = new_location
                ngx.log(ngx.INFO, "Header filter - Converted relative Location from " .. location .. " to " .. new_location)
            elseif https_port ~= "443" then
                local protocol, host, path = location:match("^(https?)://([^:/]+)(/.*)$")
                if protocol and host then
                    local new_location = protocol .. "://" .. server_name .. ":" .. https_port .. path
                    ngx.header["Location"] = new_location
                    ngx.log(ngx.INFO, "Header filter - Rewrote absolute Location from " .. location .. " to " .. new_location)
                end
            end
        end
    end

    local existing_jti = ngx.var.cookie_JTI
    if existing_jti then
        ngx.log(ngx.DEBUG, "Header filter - Cookie with JTI already present. Skipping JWT processing.")
        return
    end

    local token = ngx.var.arg_jwt
    if not token or token == "" then
        ngx.log(ngx.DEBUG, "Header filter - No JWT found in URL parameters.")
        return
    end

    local jwt_object = jwt:load_jwt(token)
    if not jwt_object.valid then
        ngx.log(ngx.WARN, "Header filter - Invalid JWT format: " .. tostring(jwt_object.reason))
        return
    end

    local public_key = dict:get("public_key")
    if not public_key then
        ngx.log(ngx.ERR, "Header filter - Public key not available; skipping JWT verification")
        return
    end

    local jwt_obj = jwt:verify_jwt_obj(public_key, jwt_object)
    if not jwt_obj or not jwt_obj.verified then
        ngx.log(ngx.WARN, "Header filter - Invalid or expired JWT signature")
        return
    end

    local jti = jwt_obj.payload.jti
    if not jti then
        ngx.log(ngx.WARN, "Header filter - JTI claim missing in JWT")
        return
    end

    local username = jwt_obj.payload.sub
    if not username then
        ngx.log(ngx.WARN, "Header filter - Username (sub) claim missing in JWT")
        return
    end
    local username_lower = string.lower(username)

    local config = ngx.shared.config
    local req_issuer = config:get("issuer")
    local issuer = jwt_obj.payload.iss
    if not issuer or issuer ~= req_issuer then
        ngx.log(ngx.WARN, "Header filter - Invalid issuer claim: " .. tostring(issuer) .. " (expected: " .. req_issuer .. ")")
        return
    end

    local https_port = config:get("https_port")
    local port_suffix = (https_port == "443") and "" or (":" .. https_port)
    local req_audience = "https://" .. config:get("server_name") .. port_suffix .. config:get("guac_uri")
    local audience = jwt_obj.payload.aud

    local function normalize_audience(url)
        if not url or url == "" then
            return url
        end
        return url:gsub("/+$", "")
    end

    local normalized_audience = normalize_audience(audience)
    local normalized_req_audience = normalize_audience(req_audience)

    if not normalized_audience or normalized_audience ~= normalized_req_audience then
        ngx.log(ngx.WARN, "Header filter - Invalid audience claim: " .. tostring(audience) ..
            " (expected: " .. req_audience .. ")")
        return
    end

    local existing_username = dict:get("username:" .. jti)
    if existing_username then
        ngx.log(ngx.DEBUG, "Header filter - JTI already registered: " .. tostring(jti))
        return
    end

    local ok, err = dict:set("username:" .. jti, username_lower, 7200)
    if not ok then
        ngx.log(ngx.ERR, "Header filter - Error storing JTI in shared dict: " .. tostring(err))
        return
    end

    ok, err = dict:set("exp:" .. username_lower, jwt_obj.payload.exp, 7200)
    if not ok then
        ngx.log(ngx.ERR, "Header filter - Error storing expiration in shared dict: " .. tostring(err))
        return
    end

    local guac_uri = config:get("guac_uri")
    local now = ngx.time()
    local max_age = jwt_obj.payload.exp - now
    if max_age < 0 then
        max_age = 0
    end
    ngx.header["Set-Cookie"] = "JTI=" .. jti .. "; Max-Age=" .. max_age .. "; Path=" .. guac_uri .. "; Secure; HttpOnly; SameSite=Lax"
    ngx.log(ngx.INFO, "Header filter - JWT validated and cookie set for " .. username .. " (expires in " .. max_age .. "s)")
end

return _M
