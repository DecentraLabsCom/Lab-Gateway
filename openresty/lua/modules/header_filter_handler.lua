local _M = {}

--- Keeps Guacamole redirects on the public gateway origin. Access credentials
-- are exchanged before this phase and are never read from a URL query string.
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    if ngx.status == 101 and ngx.var.uri and ngx.var.uri:match("/guacamole/websocket%-tunnel") then
        local reporter = (deps and deps.access_audit_reporter) or require "modules.access_audit_reporter"
        local ok, err = pcall(reporter.report_guacamole_session_observed, ngx, deps and deps.access_audit)
        if not ok then
            ngx.log(ngx.WARN, "Access audit - unable to persist websocket observation: " .. tostring(err))
        end
    end
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
