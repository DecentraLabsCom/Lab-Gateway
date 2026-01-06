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

if token == "" then
    if not is_loopback_or_docker(ngx.var.remote_addr or "") then
        return deny("Unauthorized: LAB_MANAGER_TOKEN not set; access allowed only from 127.0.0.1 or 172.16.0.0/12.")
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

local function token_hint()
    local hint = "Provide " .. header_name .. " header or " .. cookie_name .. " cookie"
    if is_lab_manager then
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
        if is_lab_manager then
            ngx.header["Set-Cookie"] = cookie_name .. "=" .. arg_token .. "; Path=/; HttpOnly; Secure; SameSite=Lax"
        end
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
        return deny("Unauthorized: invalid lab manager token. " .. token_hint())
    end
elseif not is_private(ngx.var.remote_addr or "") then
    return deny("Unauthorized: lab manager token required. " .. token_hint())
end

ngx.req.set_header(header_name, token)
