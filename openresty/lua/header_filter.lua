-- ============================================================================
-- header_filter.lua - Header Filter Phase (header_filter_by_lua)
-- ============================================================================
-- Runs when processing response HEADERS from Guacamole (before body).
-- Purpose: Extract JWT from URL parameter (?jwt=...), verify signature,
-- validate claims (iss, aud, jti), and set a short-lived JTI cookie for the
-- client. Stores JTI-username mapping in shared dict for session tracking.
-- ============================================================================

-- Load modules once per worker (cached automatically by OpenResty)
local jwt = require "resty.jwt"
local dict = ngx.shared.cache
--local http = require "resty.http"
--local cjson = require "cjson"

-- Fix Location header redirects to include correct port
local status = ngx.status
if (status == 301 or status == 302 or status == 303 or status == 307 or status == 308) then
    local location = ngx.header["Location"]
    if location then
        ngx.log(ngx.INFO, "Header filter - Detected redirect with Location: " .. location)
        
        local config = ngx.shared.config
        local https_port = config:get("https_port") or "443"
        local server_name = config:get("server_name") or "localhost"
        
        -- Handle relative paths (start with /) - convert to absolute with port
        if location:match("^/") then
            local new_location = "https://" .. server_name
            if https_port ~= "443" then
                new_location = new_location .. ":" .. https_port
            end
            new_location = new_location .. location
            ngx.header["Location"] = new_location
            ngx.log(ngx.INFO, "Header filter - Converted relative Location from " .. location .. " to " .. new_location)
        -- Handle absolute URLs missing the port (has pattern https://host/ without :port)
        elseif https_port ~= "443" and location:match("^https?://[^:]+/") then
            -- Extract protocol and path
            local protocol = location:match("^(https?)://")
            local path = location:match("^https?://[^/]+(/.*)$") or "/"
            
            -- Rebuild with port
            local new_location = protocol .. "://" .. server_name .. ":" .. https_port .. path
            ngx.header["Location"] = new_location
            ngx.log(ngx.INFO, "Header filter - Rewrote absolute Location from " .. location .. " to " .. new_location)
        end
    end
end

-- Check existing cookies first
local cookies = ngx.var.http_cookie
if cookies then
	local token = string.match(cookies, "JTI=([^;]+)")
	if token then
		ngx.log(ngx.DEBUG, "Header filter - Cookie with JTI already present. Skipping JWT processing.")
		return
	end
end

-- Get JWT from URL parameter
local token = ngx.var.arg_jwt
if not token or token == "" then
	ngx.log(ngx.DEBUG, "Header filter - No JWT found in URL parameters.")
	return
end

-- Validate JWT format before accessing shared dict
local jwt_object = jwt:load_jwt(token)
if not jwt_object.valid then
	ngx.log(ngx.WARN, "Header filter - Invalid JWT format: " .. tostring(jwt_object.reason))
	return
end

-- Only access shared dict after validating JWT format
local public_key = dict:get("public_key")
if not public_key then
	ngx.log(ngx.ERR, "Header filter - Public key not available; skipping JWT verification")
	return
end

-----------------------------------------------------------------------

-- Read public key from URL with JWKS
--local jwks_url = jwt_object.payload.iss .. "/jwks"

-- HTTP request to get the JWKS
--local httpc = http.new()
--local res, err = httpc:request_uri(jwks_url, {
--	method = "GET",
--	headers = {
--	    ["Accept"] = "application/json"
--	}
--})

--if not res then
--	ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
--	ngx.say("Failed to fetch JWKS: " .. err)
--	return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
--end

-- Decode the response's body
--local jwks = cjson.decode(res.body)

-- Get JWT's "kid" to determine which key to use if there is more than one
--local kid = jwt_object.header.kid

-- Get the right key from the JWKS
--local public_key_pem
--for _, key in ipairs(jwks.keys) do
--	if key.kid == kid then
		-- Extract public key in PEM format
--		local n = key.n
--		local e = key.e
		-- Convert to PEM format
--		public_key_pem = "-----BEGIN PUBLIC KEY-----\n" ..
--					ngx.encode_base64(n) ..
--				"\n-----END PUBLIC KEY-----"
--		break
--	end
--end

--if not public_key_pem then
--	ngx.status = ngx.HTTP_UNAUTHORIZED
--	ngx.say("Public key not found in JWKS")
--	return ngx.exit(ngx.HTTP_UNAUTHORIZED)
--end

----------------------------------------------------------------------

-- Verify JWT signature with public key
local jwt_obj = jwt:verify_jwt_obj(public_key, jwt_object)
if not jwt_obj or not jwt_obj.verified then
	ngx.log(ngx.WARN, "Header filter - Invalid or expired JWT signature")
	return
end

-- Validate JTI exists
local jti = jwt_obj.payload.jti
if not jti then
	ngx.log(ngx.WARN, "Header filter - JTI claim missing in JWT")
	return
end

-- Extract username (sub claim)
local username = jwt_obj.payload.sub
if not username then
	ngx.log(ngx.WARN, "Header filter - Username (sub) claim missing in JWT")
	return
end
local username_lower = string.lower(username)

-- Validate issuer (iss claim)
local config = ngx.shared.config
local req_issuer = config:get("issuer")
local issuer = jwt_obj.payload.iss
if not issuer or issuer ~= req_issuer then
	ngx.log(ngx.WARN, "Header filter - Invalid issuer claim: " .. tostring(issuer) .. " (expected: " .. req_issuer .. ")")
	return
end

-- Validate audience (aud claim) - include port if not 443
local https_port = config:get("https_port")
local port_suffix = (https_port == "443") and "" or (":" .. https_port)
local req_audience = "https://" .. config:get("server_name") .. port_suffix .. config:get("guac_uri")
local audience = jwt_obj.payload.aud
if not audience or audience ~= req_audience then
	ngx.log(ngx.WARN, "Header filter - Invalid audience claim: " .. tostring(audience) .. " (expected: " .. req_audience .. ")")
	return
end

-- Check if JTI is already registered (prevent replay)
local existing_username = dict:get("username:" .. jti)
if existing_username then
	ngx.log(ngx.DEBUG, "Header filter - JTI already registered: " .. tostring(jti))
	return
end

-- All validations passed, register JTI-username mapping
local ok, err = dict:set("username:" .. jti, username_lower, 7200)
if not ok then
	ngx.log(ngx.ERR, "Header filter - Error storing JTI in shared dict: " .. tostring(err))
	return
end

-- Register session expiration time
local ok, err = dict:set("exp:" .. username_lower, jwt_obj.payload.exp, 7200)
if not ok then
	ngx.log(ngx.ERR, "Header filter - Error storing expiration in shared dict: " .. tostring(err))
	return
end

-- Set JTI cookie for the client with duration matching JWT expiration
local guac_uri = config:get("guac_uri")
local now = ngx.time()
local max_age = jwt_obj.payload.exp - now
if max_age < 0 then
	max_age = 0  -- Token already expired, set cookie to expire immediately
end
ngx.header["Set-Cookie"] = "JTI=" .. jti .. "; Max-Age=" .. max_age .. "; Path=" .. guac_uri .. "; Secure; HttpOnly; SameSite=Lax"
ngx.log(ngx.INFO, "Header filter - JWT validated and cookie set for " .. username .. " (expires in " .. max_age .. "s)")
