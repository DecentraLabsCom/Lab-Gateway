-- ============================================================================
-- access.lua - Access Phase (access_by_lua)
-- ============================================================================
-- Runs BEFORE the request is proxied to Guacamole backend.
-- Purpose: Validate the JTI cookie from the client. If valid, set the
-- Authorization header with the username to be sent to Guacamole. If invalid
-- or missing, proceed without authentication (Guacamole will handle it).
-- ============================================================================

local jwt = require "resty.jwt"
local dict = ngx.shared.cache

-- Check cookies
local cookies = ngx.var.http_cookie
if not cookies or cookies == "" then
	ngx.log(ngx.INFO, "No cookie found. Proceeding to backend without header for authentication.")
        return
end

-- Extract the JWT's JTI from the cookie
local jti = string.match(cookies, "JTI=([^;]+)")
if not jti or jti == "" then
	ngx.log(ngx.INFO, "No valid cookie found. Proceeding to backend without header for authentication.")
	return
end

-- Check if JTI is in shared dict to validate the cookie
local username = dict:get("username:" .. jti)
if not username then
        ngx.log(ngx.INFO, "JTI in cookie is not valid: " .. tostring(jti))
        -- Return 401 without using ngx.say/ngx.exit which can be problematic in some contexts
        ngx.status = ngx.HTTP_UNAUTHORIZED
        ngx.header["Content-Type"] = "text/plain"
        ngx.log(ngx.WARN, "Invalid or expired cookie for JTI: " .. tostring(jti))
        return
end

-- Set Authorization header with username
ngx.req.set_header("Authorization", username)
ngx.log(ngx.INFO, "Valid cookie. Authorization header set.")
