-- Access guard for billing/wallet-facing endpoints.
-- Enforces the access token for non-local clients when configured.

local bit = require("bit")
local random = require("resty.random")
local resty_string = require("resty.string")
local token = os.getenv("ADMIN_ACCESS_TOKEN") or ""
local config = ngx.shared and ngx.shared.config
local lite_mode = config and config:get("lite_mode")

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

if lite_mode == 1 or lite_mode == true or lite_mode == "1" then
    return deny_forbidden("Forbidden: wallet/billing endpoints are disabled in Lite mode.")
end

local uri = ngx.var.uri or ""
if uri == "/wallet/health" or uri == "/billing/health" then
    return
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

local function env_bool(name, default)
    local value = os.getenv(name)
    if value == nil or value == "" then
        return default
    end
    value = tostring(value):lower()
    return value == "true" or value == "1" or value == "yes" or value == "on"
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
    local ip = value:match("^%s*([^,\\s]+)")
    if not ip or ip == "" then
        return nil
    end
    return ip
end

-- When ADMIN_TRUST_FORWARDED_IP=false the gateway is the public edge and
-- XFF headers could be spoofed by clients.  Only trust them when explicitly
-- enabled (consistent with admin_access.lua and lab_manager_access.lua).
local trust_xff = os.getenv("ADMIN_TRUST_FORWARDED_IP")
local xff_trusted = trust_xff ~= "false" and trust_xff ~= "0"

local headers = ngx.req.get_headers()
local remote_addr = ngx.var.remote_addr or ""
local forwarded_ip = extract_first_ip(headers["X-Forwarded-For"])
if not forwarded_ip then
    forwarded_ip = extract_first_ip(headers["X-Real-IP"])
end

local client_ip = remote_addr
if xff_trusted and forwarded_ip and forwarded_ip ~= "" and is_private(remote_addr) and not is_private(forwarded_ip) then
    client_ip = forwarded_ip
end

local function network_policy_allows()
    local local_only = env_bool("ADMIN_DASHBOARD_LOCAL_ONLY", true)
    if not local_only then
        return true
    end
    if is_loopback_or_docker(client_ip) then
        return true
    end
    local private_enabled = env_bool("ADMIN_DASHBOARD_ALLOW_PRIVATE", false)
        and env_bool("SECURITY_ALLOW_PRIVATE_NETWORKS", false)
    return private_enabled and configured_cidr_matches(client_ip)
end

if token == "" then
    if not is_loopback(client_ip) then
        return deny("Forbidden: Remote access is disabled. To enable external access, set ADMIN_ACCESS_TOKEN in your .env file and restart the service.")
    end
    return
end

if not network_policy_allows() then
    return deny_forbidden("Forbidden: Wallet and billing access is disabled for this network by dashboard access policy.")
end

local header_name = os.getenv("ADMIN_ACCESS_TOKEN_HEADER") or "X-Access-Token"
local cookie_name = os.getenv("ADMIN_ACCESS_TOKEN_COOKIE") or "access_token"
local csrf_cookie_name = os.getenv("ADMIN_CSRF_COOKIE") or "dlabs_csrf"
local csrf_header_name = os.getenv("ADMIN_CSRF_HEADER") or "X-CSRF-Token"
local csrf_max_age = 900

local function is_tokenized_path(value)
    if not value or value == "" then
        return false
    end
    for _, prefix in ipairs({ "/wallet-dashboard", "/institution-config" }) do
        if value:sub(1, #prefix) == prefix then
            local next_char = value:sub(#prefix + 1, #prefix + 1)
            if next_char == "" or next_char == "/" or next_char == "?" then
                return true
            end
        end
    end
    return false
end

local request_uri = ngx.var.request_uri or ""
local is_tokenized_request = is_tokenized_path(uri) or is_tokenized_path(request_uri)

local function token_hint()
    return "Provide " .. header_name .. " header or " .. cookie_name
        .. " cookie. Query-string tokens are disabled; use POST /admin/login."
end

if is_tokenized_request and ngx.var.arg_token and ngx.var.arg_token ~= "" then
    ngx.status = 400
    ngx.header["Content-Type"] = "text/plain"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.say("Query-string tokens are disabled; authenticate with POST /admin/login.")
    return ngx.exit(400)
end

local provided = headers[header_name]
local session_id
if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    session_id = ngx.var[cookie_var]
    if session_id and session_id ~= "" and ngx.shared.cache then
        provided = ngx.shared.cache:get("admin_session:billing:" .. session_id)
    end
end

if provided and provided ~= "" then
    if not constant_time_eq(provided, token) then
        return deny("Unauthorized: Invalid access token. " .. token_hint())
    end
elseif not is_loopback(client_ip) then
    return deny("Unauthorized: Access token required for remote access. " .. token_hint())
end

-- Browser sessions use an opaque HttpOnly cookie. Bind a separate,
-- non-HttpOnly token to that session and require it on state-changing calls.
-- Direct service calls using the configured header remain machine-to-machine
-- requests and are not exposed to browser CSRF.
if session_id and ngx.shared.cache then
    local csrf_key = "admin_csrf:billing:" .. session_id
    local expected_csrf = ngx.shared.cache:get(csrf_key)
    local csrf_cookie = ngx.var["cookie_" .. csrf_cookie_name]
    local method = ngx.req.get_method()

    if not expected_csrf then
        if method ~= "GET" and method ~= "HEAD" then
            return deny_forbidden("Forbidden: establish an administrative session before modifying data.")
        end
        local csrf_bytes = random.bytes(32, true)
        if not csrf_bytes then
            return deny_forbidden("Forbidden: CSRF protection is unavailable.")
        end
        expected_csrf = resty_string.to_hex(csrf_bytes)
        if not ngx.shared.cache:set(csrf_key, expected_csrf, csrf_max_age) then
            return deny_forbidden("Forbidden: CSRF protection is unavailable.")
        end
    end

    if not csrf_cookie or csrf_cookie == "" then
        if method ~= "GET" and method ~= "HEAD" then
            return deny_forbidden("Forbidden: CSRF token required.")
        end
        ngx.header["Set-Cookie"] = csrf_cookie_name .. "=" .. expected_csrf
            .. "; Max-Age=" .. csrf_max_age .. "; Path=/; Secure; SameSite=Strict"
    elseif not constant_time_eq(csrf_cookie, expected_csrf) then
        return deny_forbidden("Forbidden: invalid CSRF token.")
    end

    if method == "POST" or method == "PUT" or method == "PATCH" or method == "DELETE" then
        local provided_csrf = headers[csrf_header_name]
        if not provided_csrf or not constant_time_eq(provided_csrf, expected_csrf) then
            return deny_forbidden("Forbidden: CSRF token required.")
        end
    end
end

ngx.req.set_header(header_name, token)
