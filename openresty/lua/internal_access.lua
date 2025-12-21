-- Internal access guard for wallet/treasury endpoints.
-- Enforces an internal token for non-local clients when configured.

local token = os.getenv("SECURITY_INTERNAL_TOKEN") or ""
if token == "" then
    return
end

local header_name = os.getenv("SECURITY_INTERNAL_TOKEN_HEADER") or "X-Internal-Token"
local cookie_name = os.getenv("SECURITY_INTERNAL_TOKEN_COOKIE") or "internal_token"

local headers = ngx.req.get_headers()
local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

local function is_private(ip)
    if not ip or ip == "" then
        return false
    end
    if ip == "::1" or ip == "0:0:0:0:0:0:0:1" then
        return true
    end
    if ip:match("^127%.") then
        return true
    end
    if ip:match("^10%.") then
        return true
    end
    if ip:match("^192%.168%.") then
        return true
    end
    local octet = ip:match("^172%.(%d+)%.")
    if octet then
        local n = tonumber(octet)
        if n and n >= 16 and n <= 31 then
            return true
        end
    end
    if ip:match("^169%.254%.") then
        return true
    end
    return false
end

if provided and provided ~= "" then
    if provided ~= token then
        ngx.status = ngx.HTTP_UNAUTHORIZED
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Unauthorized")
        return ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end
elseif not is_private(ngx.var.remote_addr or "") then
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Unauthorized")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

ngx.req.set_header(header_name, token)
