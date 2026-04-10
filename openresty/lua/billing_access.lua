-- Access guard for billing/wallet-facing endpoints.
-- Enforces the access token for non-local clients when configured.

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

if lite_mode == 1 or lite_mode == true or lite_mode == "1" then
    return deny_forbidden("Forbidden: wallet/billing endpoints are disabled in Lite mode.")
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
    local ip = value:match("^%s*([^,\\s]+)")
    if not ip or ip == "" then
        return nil
    end
    return ip
end

local headers = ngx.req.get_headers()
local remote_addr = ngx.var.remote_addr or ""
local forwarded_ip = extract_first_ip(headers["X-Forwarded-For"])
if not forwarded_ip then
    forwarded_ip = extract_first_ip(headers["X-Real-IP"])
end

local client_ip = remote_addr
if forwarded_ip and forwarded_ip ~= "" and is_private(remote_addr) and not is_private(forwarded_ip) then
    client_ip = forwarded_ip
end

if token == "" then
    if not is_loopback_or_docker(client_ip) then
        return deny("Forbidden: Remote access is disabled. To enable external access, set ADMIN_ACCESS_TOKEN in your .env file and restart the service.")
    end
    return
end

local header_name = os.getenv("ADMIN_ACCESS_TOKEN_HEADER") or os.getenv("TREASURY_TOKEN_HEADER") or "X-Access-Token"
local cookie_name = os.getenv("ADMIN_ACCESS_TOKEN_COOKIE") or os.getenv("TREASURY_TOKEN_COOKIE") or "access_token"

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

local uri = ngx.var.uri or ""
local request_uri = ngx.var.request_uri or ""
local is_tokenized_request = is_tokenized_path(uri) or is_tokenized_path(request_uri)

local function build_query_without_token()
    if not ngx or not ngx.req or type(ngx.req.get_uri_args) ~= "function" then
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
    local target = uri ~= "" and uri or "/wallet-dashboard/"
    local query = build_query_without_token()
    if query and query ~= "" then
        target = target .. "?" .. query
    end
    return ngx.redirect(target, 302)
end

local function get_arg_token()
    if not ngx or not ngx.req or type(ngx.req.get_uri_args) ~= "function" then
        return nil
    end

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

local function token_hint()
    local hint = "Provide " .. header_name .. " header, " .. cookie_name .. " cookie, or ?token=... query parameter"
    return hint .. "."
end

local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

local arg_token = get_arg_token()
if not provided or provided == "" then
    if is_tokenized_request and arg_token and arg_token ~= "" then
        if ngx.unescape_uri then
            arg_token = ngx.unescape_uri(arg_token)
        end
        provided = arg_token
        ngx.ctx = ngx.ctx or {}
        ngx.ctx.billing_query_token = true
    end
end

if provided and provided ~= "" then
    if provided ~= token then
        return deny("Unauthorized: Invalid access token. " .. token_hint())
    end
    if is_tokenized_request and ngx.ctx and ngx.ctx.billing_query_token then
        ngx.header["Set-Cookie"] = cookie_name .. "=" .. provided .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
        return redirect_without_token()
    end
elseif not is_private(client_ip) then
    return deny("Unauthorized: Access token required for remote access. " .. token_hint())
end

ngx.req.set_header(header_name, token)
