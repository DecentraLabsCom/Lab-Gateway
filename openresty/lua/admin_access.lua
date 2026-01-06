-- Strict access guard for treasury admin endpoints.
-- Requires a valid access token when configured; falls back to loopback/Docker only when missing.

local token = os.getenv("SECURITY_ACCESS_TOKEN") or ""

local header_name = os.getenv("SECURITY_ACCESS_TOKEN_HEADER") or "X-Access-Token"
local cookie_name = os.getenv("SECURITY_ACCESS_TOKEN_COOKIE") or "access_token"

local function deny(message)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message or "Unauthorized")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local function is_loopback_or_docker(ip)
    if not ip or ip == "" then
        return false
    end
    if ip == "::1" or ip == "0:0:0:0:0:0:0:1" then
        return true
    end
    if ip:match("^127%.") then
        return true
    end
    local octet = ip:match("^172%.(%d+)%.")
    if octet then
        local n = tonumber(octet)
        if n and n >= 16 and n <= 31 then
            return true
        end
    end
    return false
end

if token == "" then
    if not is_loopback_or_docker(ngx.var.remote_addr or "") then
        return deny("Forbidden: Remote access is disabled. To enable external access, set SECURITY_ACCESS_TOKEN in your .env file and restart the service.")
    end
    return
end

local function get_arg_token()
    local args = ngx.req.get_uri_args()
    local token_arg = args and args.token
    if not token_arg then
        return nil
    end
    if type(token_arg) == "table" then
        token_arg = token_arg[1]
    end
    if token_arg == "" then
        return nil
    end
    return token_arg
end

local headers = ngx.req.get_headers()
local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

-- Also check ?token=... query parameter
if not provided or provided == "" then
    local arg_token = get_arg_token()
    if arg_token and arg_token ~= "" then
        if ngx.unescape_uri then
            arg_token = ngx.unescape_uri(arg_token)
        end
        provided = arg_token
        -- Set cookie for subsequent requests
        ngx.header["Set-Cookie"] = cookie_name .. "=" .. arg_token .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
    end
end

if not provided or provided == "" then
    return deny("Unauthorized: Access token required. Provide " .. header_name .. " header, " .. cookie_name .. " cookie, or ?token=... query parameter.")
end

if provided ~= token then
    return deny("Unauthorized: Invalid access token. Provide " .. header_name .. " header, " .. cookie_name .. " cookie, or ?token=... query parameter.")
end

ngx.req.set_header(header_name, token)
