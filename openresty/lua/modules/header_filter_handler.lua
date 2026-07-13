local _M = {}

--- Keeps Guacamole redirects on the public gateway origin. Access credentials
-- are exchanged before this phase and are never read from a URL query string.
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    if ngx.status == 101 and ngx.var.uri and ngx.var.uri:match("/guacamole/websocket%-tunnel") then
        local reporter = (deps and deps.access_audit_reporter) or require "modules.access_audit_reporter"
        local ok, persisted, err = pcall(
            reporter.report_guacamole_session_observed,
            ngx,
            deps and deps.access_audit
        )
        if not ok or not persisted then
            ngx.log(
                ngx.ERR,
                "Access audit - refusing websocket without durable observation: " .. tostring(err or persisted)
            )
            ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE or 503
            ngx.header["Upgrade"] = nil
            ngx.header["Connection"] = nil
            ngx.header["Sec-WebSocket-Accept"] = nil
            ngx.header["Content-Length"] = nil
            return
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
