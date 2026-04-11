-- Strict access guard for billing admin endpoints.
-- Uses ADMIN_ACCESS_TOKEN. If unset, allows loopback/Docker ranges only.

local token = os.getenv("ADMIN_ACCESS_TOKEN") or ""
local config = ngx.shared and ngx.shared.config
local lite_mode = config and config:get("lite_mode")

local header_name = os.getenv("ADMIN_ACCESS_TOKEN_HEADER") or "X-Access-Token"
local cookie_name = os.getenv("ADMIN_ACCESS_TOKEN_COOKIE") or "access_token"

local function deny(message)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message or "Unauthorized")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local function deny_forbidden(message)
    ngx.status = 403
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message or "Forbidden")
    return ngx.exit(403)
end

if lite_mode == 1 or lite_mode == true or lite_mode == "1" then
    return deny_forbidden("Forbidden: billing admin endpoints are disabled in Lite mode.")
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

local function extract_first_ip(value)
    if not value then
        return nil
    end
    if type(value) == "table" then
        value = value[1]
    end
    if not value or value == "" then
        return nil
    end
    local ip = value:match("^%s*([^,%s]+)")
    if not ip or ip == "" then
        return nil
    end
    return ip
end

local headers = ngx.req.get_headers()
local remote_addr = ngx.var.remote_addr or ""

-- When ADMIN_TRUST_FORWARDED_IP=false the gateway is the public edge and
-- XFF headers MUST NOT be trusted for access-control decisions.
local trust_xff = os.getenv("ADMIN_TRUST_FORWARDED_IP")
trust_xff = (trust_xff == nil or trust_xff == "" or trust_xff ~= "false")

local forwarded_ip = nil
if trust_xff then
    forwarded_ip = extract_first_ip(headers["X-Forwarded-For"])
    if not forwarded_ip then
        forwarded_ip = extract_first_ip(headers["X-Real-IP"])
    end
end

local client_ip = remote_addr
if forwarded_ip and forwarded_ip ~= "" and is_private(remote_addr) and not is_private(forwarded_ip) then
    client_ip = forwarded_ip
end

if token == "" then
    if not is_loopback_or_docker(client_ip) then
        return deny("Forbidden: Remote billing admin access is disabled. Set ADMIN_ACCESS_TOKEN in your .env file and restart the service.")
    end
    return
end

local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

if not provided or provided == "" then
    return deny("Unauthorized: Access token required. Provide " .. header_name .. " header or " .. cookie_name .. " cookie.")
end

if provided ~= token then
    return deny("Unauthorized: Invalid access token. Provide " .. header_name .. " header or " .. cookie_name .. " cookie.")
end

-- Always forward the selected token header
ngx.req.set_header(header_name, token)

-- Ensure downstream always receives X-Access-Token.
if header_name ~= "X-Access-Token" then
    ngx.req.set_header("X-Access-Token", token)
end
