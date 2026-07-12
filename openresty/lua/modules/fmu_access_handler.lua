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
    local session_id = cookie_value(ngx.var.http_cookie, "FMU_SESSION")
    if not session_id or session_id == "" then
        return false
    end
    local cache = ngx.shared.cache
    local token = cache:get("fmu_access_token:" .. session_id)
    local exp = tonumber(cache:get("fmu_access_exp:" .. session_id))
    if not token or not exp or ngx.time() >= exp then
        ngx.status = ngx.HTTP_UNAUTHORIZED
        ngx.say("FMU access session expired")
        return ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end
    ngx.req.set_header("Authorization", "Bearer " .. token)
    return true
end

return _M
