local _M = {}

---Processes the access phase logic that validates the JTI cookie and
-- propagates the username to Guacamole when it is still valid.
-- @param ngx_ctx table Optional ngx-like context (defaults to global ngx).
function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache

    local cookies = ngx.var.http_cookie
    if not cookies or cookies == "" then
        ngx.log(ngx.DEBUG, "Access - No cookie found. Proceeding to backend without header for authentication.")
        return
    end

    local jti = string.match(cookies, "JTI=([^;]+)")
    if not jti or jti == "" then
        ngx.log(ngx.DEBUG, "Access - No valid JTI cookie found. Proceeding to backend without header for authentication.")
        return
    end

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
end

return _M
