local _M = {}

--- Keeps Guacamole redirects on the public gateway origin. Access credentials
-- are exchanged before this phase and are never read from a URL query string.
function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx
    local status = ngx.status
    if status ~= 301 and status ~= 302 and status ~= 303 and status ~= 307 and status ~= 308 then
        return
    end
    local location = ngx.header["Location"]
    if not location then return end
    if location:sub(1, 1) == "/" then
        local config = ngx.shared.config
        local port = config:get("https_port") or "443"
        local origin = "https://" .. (config:get("server_name") or "localhost")
        if port ~= "443" then origin = origin .. ":" .. port end
        ngx.header["Location"] = origin .. location
    end
end

return _M
