-- Strict internal access guard for treasury admin endpoints.
-- Requires a valid internal token when configured; falls back to loopback/Docker only when missing.

local token = os.getenv("SECURITY_INTERNAL_TOKEN") or ""

local header_name = os.getenv("SECURITY_INTERNAL_TOKEN_HEADER") or "X-Internal-Token"
local cookie_name = os.getenv("SECURITY_INTERNAL_TOKEN_COOKIE") or "internal_token"

local function deny()
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Unauthorized")
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
        return deny()
    end
    return
end

local headers = ngx.req.get_headers()
local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

if not provided or provided == "" then
    return deny()
end

if provided ~= token then
    return deny()
end

ngx.req.set_header(header_name, token)
