-- Lab Manager access guard.
-- Enforces a dedicated access token for non-local clients when configured.

local bit = require("bit")
local token = os.getenv("LAB_MANAGER_TOKEN") or ""

local function deny(message)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message or "Unauthorized")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
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
local trust_xff_env = os.getenv("ADMIN_TRUST_FORWARDED_IP")
local trust_xff = (trust_xff_env == nil or trust_xff_env == "" or trust_xff_env ~= "false")

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

local function tokenless_network_allows()
    return is_loopback(client_ip)
end

if token == "" then
    if not tokenless_network_allows() then
        return deny("Unauthorized: LAB_MANAGER_TOKEN not set; access allowed only from loopback.")
    end
    return
end

if not network_policy_allows() then
    return deny("Unauthorized: Lab Manager access is disabled for this network by dashboard access policy.")
end

local header_name = os.getenv("LAB_MANAGER_TOKEN_HEADER") or "X-Lab-Manager-Token"
local cookie_name = os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token"

local function is_lab_manager_path(value)
    if not value or value == "" then
        return false
    end
    local prefix = "/lab-manager"
    if value:sub(1, #prefix) ~= prefix then
        return false
    end
    local next_char = value:sub(#prefix + 1, #prefix + 1)
    return next_char == "" or next_char == "/" or next_char == "?"
end

local uri = ngx.var.uri or ""
local request_uri = ngx.var.request_uri or ""
local is_lab_manager = is_lab_manager_path(uri) or is_lab_manager_path(request_uri)

local function build_query_without_token()
    if not ngx.req.get_uri_args then
        return nil
    end
    local args = ngx.req.get_uri_args() or {}
    args.token = nil
    if next(args) == nil then
        return nil
    end
    if ngx.encode_args then
        return ngx.encode_args(args)
    end
    local parts = {}
    for key, value in pairs(args) do
        if type(value) == "table" then
            for _, item in ipairs(value) do
                parts[#parts + 1] = tostring(key) .. "=" .. tostring(item)
            end
        else
            parts[#parts + 1] = tostring(key) .. "=" .. tostring(value)
        end
    end
    return table.concat(parts, "&")
end

local function redirect_without_token()
    local target = uri ~= "" and uri or "/lab-manager/"
    local query = build_query_without_token()
    if query and query ~= "" then
        target = target .. "?" .. query
    end
    return ngx.redirect(target, 302)
end

local function token_hint()
    local hint = "Provide " .. header_name .. " header or " .. cookie_name .. " cookie"
    if is_lab_manager then
        hint = hint .. " (or ?token=...)"
    end
    return hint .. "."
end

local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

local function extract_token_from_args(args)
    if not args or args == "" then
        return nil
    end
    args = args:gsub("^%?", "")
    local token_value = ("&" .. args):match("&token=([^&]+)")
    if token_value and token_value ~= "" then
        return token_value
    end
    return nil
end

if not provided or provided == "" then
    local arg_token = ngx.var.arg_token
    if not arg_token or arg_token == "" then
        if ngx.req.get_uri_args then
            local uri_args = ngx.req.get_uri_args()
            local token_arg = uri_args and uri_args.token
            if type(token_arg) == "table" then
                token_arg = token_arg[1]
            end
            if token_arg and token_arg ~= "" then
                arg_token = tostring(token_arg)
            end
        end
    end
    local used_query_token = false
    if is_lab_manager then
        if not arg_token or arg_token == "" then
            local args = ngx.var.args or ""
            arg_token = extract_token_from_args(args)
        end
        if not arg_token or arg_token == "" then
            local request_uri = ngx.var.request_uri or ""
            local query = request_uri:match("%?(.*)$") or ""
            arg_token = extract_token_from_args(query)
        end
        if arg_token and arg_token ~= "" then
            if ngx.unescape_uri then
                arg_token = ngx.unescape_uri(arg_token)
            end
            provided = arg_token
            used_query_token = true
        end
    end

    if used_query_token then
        ngx.ctx = ngx.ctx or {}
        ngx.ctx.lab_manager_query_token = true
    end
end

if provided and provided ~= "" then
    if not constant_time_eq(provided, token) then
        return deny("Unauthorized: invalid lab manager token. " .. token_hint())
    end
    if is_lab_manager and ngx.ctx and ngx.ctx.lab_manager_query_token then
        ngx.header["Set-Cookie"] = cookie_name .. "=" .. provided .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
        return redirect_without_token()
    end
elseif not is_loopback(client_ip) then
    return deny("Unauthorized: lab manager token required. " .. token_hint())
end

ngx.req.set_header(header_name, token)
