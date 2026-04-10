-- Lab Manager access guard.
-- Enforces a dedicated access token for non-local clients when configured.

local token = os.getenv("LAB_MANAGER_TOKEN") or ""

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
local forwarded_ip = extract_first_ip(headers["X-Forwarded-For"])
if not forwarded_ip then
    forwarded_ip = extract_first_ip(headers["X-Real-IP"])
end

local client_ip = remote_addr
if forwarded_ip and forwarded_ip ~= "" and is_private(remote_addr) and not is_private(forwarded_ip) then
    client_ip = forwarded_ip
end

if token == "" then
    if not is_private(client_ip) then
        return deny("Unauthorized: LAB_MANAGER_TOKEN not set; access allowed only from loopback or RFC1918 private networks.")
    end
    return
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
    if provided ~= token then
        return deny("Unauthorized: invalid lab manager token. " .. token_hint())
    end
    if is_lab_manager and ngx.ctx and ngx.ctx.lab_manager_query_token then
        ngx.header["Set-Cookie"] = cookie_name .. "=" .. provided .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
        return redirect_without_token()
    end
elseif not is_private(client_ip) then
    return deny("Unauthorized: lab manager token required. " .. token_hint())
end

ngx.req.set_header(header_name, token)
