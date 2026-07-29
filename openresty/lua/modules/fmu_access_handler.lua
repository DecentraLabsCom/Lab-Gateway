local _M = {}
local access_store = require "modules.fmu_access_store"

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

function _M.run(ngx_ctx, dependencies)
    local ngx = ngx_ctx or ngx
    local store = (dependencies and dependencies.store) or access_store.default
    local session_id = cookie_value(ngx.var.http_cookie, "FMU_SESSION")
    if not session_id or session_id == "" then
        return false
    end
    local cache = ngx.shared.cache
    if #session_id < 16 or #session_id > 512 or not session_id:match("^[A-Za-z0-9_-]+$") then
        ngx.status = 400
        ngx.say("Invalid FMU access session")
        return ngx.exit(400)
    end
    local token = cache:get("fmu_access_token:" .. session_id)
    local exp = tonumber(cache:get("fmu_access_exp:" .. session_id))
    if not token or not exp then
        local durable_token, durable_exp, store_err = store:load(session_id, ngx.time())
        if store_err then
            ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
            ngx.say("FMU access session unavailable")
            return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
        end
        token = durable_token
        exp = tonumber(durable_exp)
        if token and exp then
            local remaining_lifetime = math.max(1, exp - ngx.time())
            cache:set("fmu_access_token:" .. session_id, token, remaining_lifetime)
            cache:set("fmu_access_exp:" .. session_id, exp, remaining_lifetime)
        end
    end
    if not token or not exp or ngx.time() >= exp then
        ngx.status = ngx.HTTP_UNAUTHORIZED
        ngx.say("FMU access session expired")
        return ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end
    ngx.req.set_header("Authorization", "Bearer " .. token)
    return true
end

return _M
