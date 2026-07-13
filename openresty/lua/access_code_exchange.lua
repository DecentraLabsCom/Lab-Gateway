local cjson = require "cjson.safe"
local http = require "resty.http"
local jwt = require "resty.jwt"

local function fail(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.say(message)
    return ngx.exit(status)
end

if ngx.req.get_method() ~= "POST" then
    return fail(405, "Method not allowed")
end

ngx.req.read_body()
local args, err = ngx.req.get_post_args(4)
if not args or err then
    return fail(400, "Invalid request")
end
local access_code = args.access_code
if type(access_code) ~= "string" or access_code == "" or #access_code > 256 then
    return fail(400, "Missing access code")
end

local configured_redeem_url = os.getenv("AUTH_ACCESS_CODE_REDEEM_URL")
local redeem_url = configured_redeem_url and configured_redeem_url ~= "" and configured_redeem_url or nil
if not redeem_url then
    local config = ngx.shared.config
    local issuer = (config and config:get("issuer")) or ""
    local port = (config and config:get("https_port")) or "443"
    local local_issuer = "https://" .. ((config and config:get("server_name")) or "localhost")
    if port ~= "443" then local_issuer = local_issuer .. ":" .. port end
    local_issuer = local_issuer .. "/auth"
    if issuer ~= "" and issuer:gsub("/+$", "") ~= local_issuer:gsub("/+$", "") then
        redeem_url = issuer:gsub("/+$", "") .. "/access-code/redeem"
    else
        redeem_url = "http://blockchain-services:8080/auth/access-code/redeem"
    end
end
local httpc = http.new()
httpc:set_timeout(5000)
local redeemer_token = os.getenv("AUTH_ACCESS_CODE_REDEEMER_TOKEN")
if not redeemer_token or redeemer_token == "" or string.upper(redeemer_token) == "CHANGE_ME" then
    return fail(503, "Access-code redemption is not configured")
end
local response, request_err = httpc:request_uri(redeem_url, {
    method = "POST",
    body = cjson.encode({ accessCode = access_code }),
    headers = {
        ["Content-Type"] = "application/json",
        ["X-Access-Code-Redeemer-Token"] = redeemer_token,
        ["X-Gateway-ID"] = tostring(ngx.shared.config:get("server_name") or ""),
    },
    ssl_verify = true,
})
if not response then
    ngx.log(ngx.ERR, "Access-code redemption unavailable: ", tostring(request_err))
    return fail(502, "Access service unavailable")
end
if response.status ~= 200 then
    return fail(response.status == 401 and 401 or 502, "Invalid or expired access code")
end

local payload = cjson.decode(response.body or "")
local token = payload and payload.token
local lab_url = payload and payload.labURL
if type(token) ~= "string" or token == "" or type(lab_url) ~= "string" or lab_url == "" then
    return fail(502, "Invalid access service response")
end

local cache = ngx.shared.cache
local public_key = cache:get("public_key")
if not public_key then
    return fail(503, "Authentication key unavailable")
end
local parsed = jwt:load_jwt(token)
if not parsed.valid then
    return fail(401, "Invalid access credential")
end
local verified = jwt:verify_jwt_obj(public_key, parsed)
if not verified or not verified.verified then
    return fail(401, "Invalid access credential")
end
local claims = verified.payload or {}
local jti = claims.jti
local username = claims.sub
local exp = tonumber(claims.exp)
if not jti or not username or not exp or exp <= ngx.time() then
    return fail(401, "Expired access credential")
end
local config = ngx.shared.config
local expected_issuer = config:get("issuer")
if not claims.iss or claims.iss:gsub("/+$", "") ~= tostring(expected_issuer):gsub("/+$", "") then
    return fail(401, "Invalid access credential issuer")
end
local nbf = tonumber(claims.nbf)
if nbf and ngx.time() < nbf then
    return fail(401, "Access credential not yet valid")
end
local port = config:get("https_port") or "443"
local port_suffix = port == "443" and "" or (":" .. port)
local gateway_origin = "https://" .. (config:get("server_name") or "localhost") .. port_suffix
local resource_type = tostring(claims.resourceType or "")
local expected_audience = resource_type == "fmu" and lab_url or (gateway_origin .. "/guacamole")
local function normalize_url(value)
    return value and tostring(value):gsub("/+$", "") or value
end
if normalize_url(claims.aud) ~= normalize_url(expected_audience) then
    return fail(401, "Invalid access credential audience")
end

-- Only redirect within this gateway; validate this before setting any session cookie.
local scheme, host, path = lab_url:match("^(https?)://([^/]+)(/[^?#]*)")
local current_host = ngx.var.http_host or ngx.var.host
if not scheme or not host or (host ~= ngx.var.host and host ~= current_host) then
    return fail(400, "Invalid lab redirect")
end
if resource_type == "fmu" and not path:match("^/fmu[/]?") then
    return fail(400, "Invalid FMU destination")
elseif resource_type ~= "fmu" and resource_type ~= "lab" then
    return fail(400, "Unsupported access resource")
end

local username_lower = string.lower(username)
local remaining_lifetime = math.max(1, exp - ngx.time())
local token_security_retention = tonumber(config:get("guac_token_security_retention_seconds")) or 1200
local enforcement_lifetime = remaining_lifetime + math.max(1, token_security_retention)
if resource_type == "fmu" then
    cache:set("fmu_access_token:" .. jti, token, remaining_lifetime)
    cache:set("fmu_access_exp:" .. jti, exp, remaining_lifetime)
    ngx.header["Set-Cookie"] = "FMU_SESSION=" .. jti
        .. "; Max-Age=" .. remaining_lifetime
        .. "; Path=/fmu; Secure; HttpOnly; SameSite=Lax"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.status = 204
    return ngx.exit(204)
end
---@diagnostic disable-next-line: redundant-parameter
cache:set("username:" .. jti, username_lower, remaining_lifetime)
---@diagnostic disable-next-line: redundant-parameter
cache:set("exp:" .. username_lower, exp, remaining_lifetime)
---@diagnostic disable-next-line: redundant-parameter
cache:set("guac_enforcement_exp:" .. username_lower, exp, enforcement_lifetime)
if claims.reservationKey then
    ---@diagnostic disable-next-line: redundant-parameter
    cache:set("reservation:" .. jti, claims.reservationKey, remaining_lifetime)
end
ngx.header["Set-Cookie"] = "JTI=" .. jti .. "; Max-Age=" .. remaining_lifetime .. "; Path=/guacamole; Secure; HttpOnly; SameSite=Lax"
ngx.header["Referrer-Policy"] = "no-referrer"

ngx.status = 303
ngx.header["Location"] = path ~= "" and path or "/guacamole/"
return ngx.exit(303)
