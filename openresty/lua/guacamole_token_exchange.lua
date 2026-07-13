local handler = require "modules.guacamole_token_handler"

local function emit(response)
    response = response or {
        status = 502,
        body = '{"message":"Guacamole authentication is unavailable"}',
        header = { ["Content-Type"] = "application/json" },
    }
    ngx.status = response.status or 502
    ngx.header["Content-Type"] = (response.header and
        (response.header["Content-Type"] or response.header["content-type"])) or "application/json"
    ngx.header["Cache-Control"] = response.header and
        (response.header["Cache-Control"] or response.header["cache-control"]) or nil
    ngx.header["Content-Length"] = nil
    ngx.print(response.body or "")
end

if ngx.req.get_method() ~= "POST" then
    ngx.header["Allow"] = "POST"
    return emit({
        status = 405,
        body = '{"message":"Method not allowed"}',
        header = { ["Content-Type"] = "application/json" },
    })
end

ngx.req.read_body()
local ok, upstream = pcall(ngx.location.capture, "/__guacamole_tokens", {
    method = ngx.HTTP_POST,
    always_forward_body = true,
})
if not ok or not upstream then
    ngx.log(ngx.ERR, "Guacamole token - Upstream request failed: " .. tostring(upstream))
    return emit(nil)
end

return emit(handler.handle_response(ngx, upstream))
