local _M = {}

local function cookie_value(cookies, name)
    if not cookies then
        return nil
    end
    for pair in tostring(cookies):gmatch("[^;]+") do
        local key, value = pair:match("^%s*([^=]+)=([^;]*)$")
        if key == name then
            return value
        end
    end
    return nil
end

function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx
    if ngx.req.get_method() ~= "POST" then
        ngx.status = 405
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Method not allowed")
        return ngx.exit(405)
    end

    local session_id = cookie_value(ngx.var.http_cookie, "FMU_SESSION")
    if session_id and (#session_id < 16 or #session_id > 512 or not session_id:match("^[A-Za-z0-9_-]+$")) then
        ngx.status = 400
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Invalid FMU session")
        return ngx.exit(400)
    end

    if session_id then
        local cache = ngx.shared.cache
        cache:delete("fmu_access_token:" .. session_id)
        cache:delete("fmu_access_exp:" .. session_id)
    end

    ngx.status = 204
    return ngx.exit(204)
end

return _M
