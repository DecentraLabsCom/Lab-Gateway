local _M = {}

local function is_websocket_tunnel(uri)
    return uri and uri:match("/guacamole/websocket%-tunnel")
end

local function is_connection_active(status)
    return status == "101"
end

local function is_auto_logout_enabled(config)
    return config and config:get("auto_logout_on_disconnect")
end

local function extract_username_from_token(dict, args)
    if not args then
        return nil
    end
    local token = args:match("token=([^&]+)")
    if not token then
        return nil
    end
    return dict:get("guac_token:" .. token)
end

function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx
    local uri = ngx.var.uri
    if not is_websocket_tunnel(uri) then
        return
    end

    local status = ngx.var.status
    if is_connection_active(status) then
        return
    end

    local config = ngx.shared.config
    if not is_auto_logout_enabled(config) then
        ngx.log(ngx.DEBUG, "Log - Auto-logout on disconnect is disabled")
        return
    end

    local username = ngx.var.http_authorization
    local dict = ngx.shared.cache

    if not username or username == "" then
        local derived = extract_username_from_token(dict, ngx.var.args)
        if derived then
            ngx.log(ngx.DEBUG, "Log - Found username from token: " .. derived)
        end
        username = derived
    end

    if not username or username == "" then
        ngx.log(ngx.DEBUG, "Log - No username found for tunnel closure")
        return
    end

    username = string.lower(username)

    local admin_user = config and config:get("admin_user")
    if admin_user and username == string.lower(admin_user) then
        ngx.log(ngx.DEBUG, "Log - Skipping tunnel closure for admin user: " .. username)
        return
    end

    if dict:get("exp:" .. username) then
        ngx.log(ngx.DEBUG, "Log - Skipping JWT-authenticated user: " .. username)
        return
    end

    local now = ngx.time()
    dict:set("tunnel_closed:" .. username, now, 300)
    dict:set("has_pending_closures", "1", 300)
    dict:set("pending_user:" .. username, "1", 300)

    ngx.log(ngx.INFO, "Log - Tunnel closed for user: " .. username .. " (status: " .. tostring(status) .. "), marked for session revocation")
end

return _M
