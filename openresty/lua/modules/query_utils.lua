-- Shared helpers for stripping the bootstrap ?token= parameter from URLs
-- and redirecting to the clean path.  Used by the exact-path bootstrap
-- blocks in lab_access.conf (/lab-manager, /wallet-dashboard,
-- /institution-config) and by billing_access.lua / lab_manager_access.lua.

local _M = {}

--- Return a URL-encoded query string with the `token` key removed.
-- Returns nil when no other parameters remain.
function _M.build_query_without_token()
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

--- Redirect to `target` (trailing-slash form), preserving any non-token
-- query parameters.  Issues a 302 response.
function _M.redirect_without_token(target)
    local query = _M.build_query_without_token()
    if query and query ~= "" then
        target = target .. "?" .. query
    end
    return ngx.redirect(target, 302)
end

return _M
