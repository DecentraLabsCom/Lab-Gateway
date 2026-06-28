-- Strict Lab Manager admin guard.
-- Requires a valid LAB_MANAGER_TOKEN header or cookie for privileged admin routes.

local bit = require("bit")
local token = os.getenv("LAB_MANAGER_TOKEN") or ""
local header_name = os.getenv("LAB_MANAGER_TOKEN_HEADER") or "X-Lab-Manager-Token"
local cookie_name = os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token"
local embedded_backend = "http://blockchain-services:8080"

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

local function trim(value)
    return tostring(value or ""):match("^%s*(.-)%s*$")
end

local function normalize_backend_url(value)
    local url = trim(value)
    if url == "" then
        return ""
    end
    return url:gsub("/+$", "")
end

local function is_loopback_host(host)
    if not host or host == "" then
        return false
    end
    local normalized = host:lower()
    return normalized == "localhost"
        or normalized == "127.0.0.1"
        or normalized == "::1"
        or normalized == "[::1]"
end

local function parse_backend_url(url)
    local scheme, host = tostring(url or ""):match("^(https?)://([^/:]+)")
    return scheme, host
end

local function resolve_backend_url()
    local configured = normalize_backend_url(os.getenv("LAB_ADMIN_BACKEND_URL"))
    local lite_mode = ngx.shared
        and ngx.shared.config
        and ngx.shared.config:get("lite_mode")
    local lite = lite_mode == 1 or lite_mode == true or lite_mode == "1"

    if configured == "" then
        if lite then
            return nil, "Forbidden: /lab-admin requires LAB_ADMIN_BACKEND_URL in Lite mode."
        end
        return embedded_backend, nil
    end

    local scheme, host = parse_backend_url(configured)
    if not scheme or not host then
        return nil, "Invalid LAB_ADMIN_BACKEND_URL. Use http://host:port or https://host."
    end

    local embedded = configured == embedded_backend
    local insecure_allowed = env_bool("LAB_ADMIN_BACKEND_ALLOW_INSECURE", false)
    if scheme ~= "https" and not embedded and not is_loopback_host(host) and not insecure_allowed then
        return nil, "Refusing insecure LAB_ADMIN_BACKEND_URL. Use HTTPS or set LAB_ADMIN_BACKEND_ALLOW_INSECURE=true for a trusted private link."
    end

    return configured, nil
end

local function resolve_backend_token(backend_url)
    local configured = trim(os.getenv("LAB_ADMIN_BACKEND_TOKEN"))
    if configured ~= "" then
        return configured
    end
    if backend_url == embedded_backend then
        return token
    end
    return ""
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

local backend_url, backend_error = resolve_backend_url()
if not backend_url then
    local status = ngx.HTTP_SERVICE_UNAVAILABLE
    if backend_error and backend_error:find("Forbidden:", 1, true) == 1 then
        status = ngx.HTTP_FORBIDDEN or 403
    end
    return deny(status, backend_error or "Service unavailable: lab admin backend is not configured.")
end

local backend_token = resolve_backend_token(backend_url)
if backend_token == "" then
    return deny(
        ngx.HTTP_SERVICE_UNAVAILABLE,
        "Service unavailable: LAB_ADMIN_BACKEND_TOKEN is required when /lab-admin proxies to a remote backend."
    )
end

local backend_header_name = trim(os.getenv("LAB_ADMIN_BACKEND_TOKEN_HEADER"))
if backend_header_name == "" then
    backend_header_name = header_name
end

ngx.var.backend_lab_admin = backend_url
if backend_header_name ~= header_name then
    ngx.req.clear_header(header_name)
end
ngx.req.set_header(backend_header_name, backend_token)
