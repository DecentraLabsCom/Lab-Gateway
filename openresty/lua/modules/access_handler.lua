local _M = {}

---Processes the access phase logic that validates the JTI cookie and
-- propagates the username to Guacamole when it is still valid.
-- When no JTI cookie is present the JWT supplied via the ?jwt= query
-- parameter is validated directly so that the very first request to
-- Guacamole already carries the Authorization header, preventing the
-- Angular SPA from showing the login screen.
-- @param ngx_ctx table Optional ngx-like context (defaults to global ngx).
-- @param deps    table Optional dependency overrides (e.g. { jwt = stub }).
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache

    -- ── Path 1: JTI cookie present ─────────────────────────────────────────
    local cookies = ngx.var.http_cookie
    if cookies and cookies ~= "" then
        local jti = string.match(cookies, "JTI=([^;]+)")
        if jti and jti ~= "" then
            local username = dict:get("username:" .. jti)
            if not username then
                ngx.log(ngx.DEBUG, "Access - JTI in cookie is not valid: " .. tostring(jti))
                ngx.status = ngx.HTTP_UNAUTHORIZED
                ngx.header["Content-Type"] = "text/plain"
                ngx.log(ngx.WARN, "Access - Invalid or expired cookie for JTI: " .. tostring(jti))
                return
            end

            local exp = dict:get("exp:" .. username)
            if not exp then
                ngx.log(ngx.WARN, "Access - No expiration found for user: " .. username)
                ngx.status = ngx.HTTP_UNAUTHORIZED
                ngx.header["Content-Type"] = "text/plain"
                return
            end

            local now = ngx.time()
            if now > tonumber(exp) then
                ngx.log(ngx.INFO, "Access - JWT expired for user: " .. username .. " (exp: " .. exp .. ", now: " .. now .. ")")
                ngx.status = ngx.HTTP_UNAUTHORIZED
                ngx.header["Content-Type"] = "text/plain"
                return
            end

            ngx.req.set_header("Authorization", username)
            ngx.log(ngx.INFO, "Access - Valid cookie. Authorization header set for " .. username)
            return
        end
    end

    -- ── Path 2: No JTI cookie – fall back to ?jwt= query parameter ─────────
    -- Validates the JWT so the Authorization header reaches Guacamole on the
    -- very first request, avoiding the login-screen flash.
    local token = ngx.var.arg_jwt
    if not token or token == "" then
        ngx.log(ngx.DEBUG, "Access - No cookie and no JWT found. Proceeding unauthenticated.")
        return
    end

    local jwt = (deps and deps.jwt) or require "resty.jwt"

    local jwt_object = jwt:load_jwt(token)
    if not jwt_object.valid then
        ngx.log(ngx.WARN, "Access - Invalid JWT format: " .. tostring(jwt_object.reason))
        return
    end

    local public_key = dict:get("public_key")
    if not public_key then
        ngx.log(ngx.ERR, "Access - Public key not available; skipping JWT verification")
        return
    end

    local jwt_obj = jwt:verify_jwt_obj(public_key, jwt_object)
    if not jwt_obj or not jwt_obj.verified then
        ngx.log(ngx.WARN, "Access - Invalid or expired JWT signature")
        return
    end

    local jti = jwt_obj.payload.jti
    if not jti then
        ngx.log(ngx.WARN, "Access - JTI claim missing in JWT")
        return
    end

    local username = jwt_obj.payload.sub
    if not username then
        ngx.log(ngx.WARN, "Access - Username (sub) claim missing in JWT")
        return
    end
    local username_lower = string.lower(username)

    local config = ngx.shared.config
    local req_issuer = config:get("issuer")
    local issuer = jwt_obj.payload.iss
    if not issuer or issuer ~= req_issuer then
        ngx.log(ngx.WARN, "Access - Invalid issuer claim: " .. tostring(issuer) ..
            " (expected: " .. tostring(req_issuer) .. ")")
        return
    end

    local https_port = config:get("https_port")
    local port_suffix = (https_port == "443") and "" or (":" .. https_port)
    local req_audience = "https://" .. config:get("server_name") .. port_suffix .. config:get("guac_uri")
    local audience = jwt_obj.payload.aud

    local function normalize_audience(url)
        if not url or url == "" then return url end
        return url:gsub("/+$", "")
    end

    if normalize_audience(audience) ~= normalize_audience(req_audience) then
        ngx.log(ngx.WARN, "Access - Invalid audience claim: " .. tostring(audience) ..
            " (expected: " .. req_audience .. ")")
        return
    end

    -- Store session data so that header_filter_handler can set the JTI cookie
    -- on the response without re-doing the full JWT validation.
    dict:set("username:" .. jti, username_lower, 7200)
    dict:set("exp:" .. username_lower, jwt_obj.payload.exp, 7200)

    ngx.req.set_header("Authorization", username_lower)
    ngx.log(ngx.INFO, "Access - JWT validated from URL. Authorization header set for " .. username_lower)
end

return _M
