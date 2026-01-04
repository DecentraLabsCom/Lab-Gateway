-- Internal access guard for wallet/treasury endpoints.
-- Enforces an internal token for non-local clients when configured.

local token = os.getenv("SECURITY_INTERNAL_TOKEN") or ""

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
        return deny("Unauthorized: SECURITY_INTERNAL_TOKEN not set; access allowed only from 127.0.0.1 or 172.16.0.0/12.")
    end
    return
end

local header_name = os.getenv("SECURITY_INTERNAL_TOKEN_HEADER") or "X-Internal-Token"
local cookie_name = os.getenv("SECURITY_INTERNAL_TOKEN_COOKIE") or "internal_token"
local function token_hint()
    local hint = "Provide " .. header_name .. " header or " .. cookie_name .. " cookie"
    local uri = ngx.var.uri or ""
    if uri == "/wallet-dashboard" or uri:find("^/wallet-dashboard/") then
        hint = hint .. " (or ?token=...)"
    end
    return hint .. "."
end

local headers = ngx.req.get_headers()
local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

if (not provided or provided == "") and (ngx.var.uri == "/wallet-dashboard" or ngx.var.uri:find("^/wallet-dashboard/")) then
    local arg_token = ngx.var.arg_token
    if arg_token and arg_token ~= "" then
        provided = arg_token
        ngx.header["Set-Cookie"] = cookie_name .. "=" .. arg_token .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
    end
end

local function is_private(ip)
    if not ip or ip == "" then
        return false
    end
    if is_loopback_or_docker(ip) then
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
        return deny("Unauthorized: invalid internal token. " .. token_hint())
    end
elseif not is_private(ngx.var.remote_addr or "") then
    return deny("Unauthorized: internal token required. " .. token_hint())
end

ngx.req.set_header(header_name, token)
