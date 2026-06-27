-- Strict Lab Manager admin guard.
-- Requires a valid LAB_MANAGER_TOKEN header or cookie for privileged admin routes.

local bit = require("bit")
local token = os.getenv("LAB_MANAGER_TOKEN") or ""
local header_name = os.getenv("LAB_MANAGER_TOKEN_HEADER") or "X-Lab-Manager-Token"
local cookie_name = os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token"

local function deny(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message)
    return ngx.exit(status)
end

-- Constant-time string comparison to mitigate timing side-channels on token checks.
local function constant_time_eq(a, b)
    if type(a) ~= "string" or type(b) ~= "string" then
        return false
    end
    if #a ~= #b then
        return false
    end
    local result = 0
    for i = 1, #a do
        result = bit.bor(result, bit.bxor(string.byte(a, i), string.byte(b, i)))
    end
    return result == 0
end

local function env_bool(name, default)
    local value = os.getenv(name)
    if value == nil or value == "" then
        return default
    end
    value = tostring(value):lower()
    return value == "true" or value == "1" or value == "yes" or value == "on"
end

local function is_loopback(ip)
    if not ip or ip == "" then
        return false
    end
    return ip == "::1"
        or ip == "0:0:0:0:0:0:0:1"
        or ip:match("^127%.") ~= nil
end

local function is_private(ip)
    if not ip or ip == "" then
        return false
    end
    if is_loopback(ip) then
        return true
    end
    if ip:match("^10%.") or ip:match("^192%.168%.") or ip:match("^169%.254%.") then
        return true
    end
    local octet = ip:match("^172%.(%d+)%.")
    if octet then
        local n = tonumber(octet)
        if n and n >= 16 and n <= 31 then
            return true
        end
    end
    local normalized = ip:lower()
    return normalized:match("^fc") ~= nil or normalized:match("^fd") ~= nil
end

local function extract_first_ip(value)
    if type(value) == "table" then
        value = value[1]
    end
    if not value or value == "" then
        return nil
    end
    local ip = tostring(value):match("^%s*([^,%s]+)")
    return ip ~= "" and ip or nil
end

local function ipv4_to_number(ip)
    local a, b, c, d = tostring(ip or ""):match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    a, b, c, d = tonumber(a), tonumber(b), tonumber(c), tonumber(d)
    if not a or not b or not c or not d then
        return nil
    end
    if a > 255 or b > 255 or c > 255 or d > 255 then
        return nil
    end
    return ((a * 256 + b) * 256 + c) * 256 + d
end

local function cidr_matches(ip, cidr)
    local base, prefix = tostring(cidr or ""):match("^%s*([^/%s]+)%s*/%s*(%d+)%s*$")
    prefix = tonumber(prefix)
    local ip_num = ipv4_to_number(ip)
    local base_num = ipv4_to_number(base)
    if not ip_num or not base_num or not prefix or prefix < 0 or prefix > 32 then
        return false
    end
    local size = 2 ^ (32 - prefix)
    return math.floor(ip_num / size) == math.floor(base_num / size)
end

local function configured_cidr_matches(ip)
    local raw = os.getenv("ADMIN_ALLOWED_CIDRS") or ""
    local has_cidr = false
    for cidr in raw:gmatch("[^,]+") do
        has_cidr = true
        if cidr_matches(ip, cidr) then
            return true
        end
    end
    return not has_cidr and is_private(ip)
end

local function resolve_client_ip(headers)
    local remote_addr = ngx.var.remote_addr or ""
    local trust_xff = os.getenv("ADMIN_TRUST_FORWARDED_IP")
    local xff_trusted = trust_xff ~= "false" and trust_xff ~= "0"
    if not xff_trusted then
        return remote_addr
    end

    local forwarded_ip = extract_first_ip(headers["X-Forwarded-For"]) or extract_first_ip(headers["X-Real-IP"])
    if forwarded_ip and forwarded_ip ~= "" and is_private(remote_addr) and not is_private(forwarded_ip) then
        return forwarded_ip
    end
    return remote_addr
end

local function network_policy_allows(headers)
    local local_only = env_bool("ADMIN_DASHBOARD_LOCAL_ONLY", true)
    if not local_only then
        return true
    end

    local client_ip = resolve_client_ip(headers)
    if is_loopback(client_ip) then
        return true
    end

    local private_enabled = env_bool("ADMIN_DASHBOARD_ALLOW_PRIVATE", false)
        and env_bool("SECURITY_ALLOW_PRIVATE_NETWORKS", false)
    return private_enabled and configured_cidr_matches(client_ip)
end

if token == "" then
    return deny(ngx.HTTP_SERVICE_UNAVAILABLE, "Service unavailable: LAB_MANAGER_TOKEN is not configured.")
end

local headers = ngx.req.get_headers()
if not network_policy_allows(headers) then
    return deny(ngx.HTTP_FORBIDDEN or 403, "Forbidden: Lab Manager access is disabled for this network by dashboard access policy.")
end

local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

if not provided or provided == "" then
    return deny(ngx.HTTP_UNAUTHORIZED, "Unauthorized: lab manager token required.")
end

if not constant_time_eq(provided, token) then
    return deny(ngx.HTTP_UNAUTHORIZED, "Unauthorized: invalid lab manager token.")
end

ngx.req.set_header(header_name, token)
