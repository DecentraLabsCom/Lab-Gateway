local _M = {}

local function is_json_response(content_type)
    return content_type and content_type:match("application/json")
end

local function is_json_body(body)
    return body and body ~= "" and body:match("^%s*[{%[]")
end

function _M.run(ngx_ctx, chunk, eof, deps)
    local ngx = ngx_ctx or ngx
    local cjson = (deps and deps.cjson) or require "cjson"

    ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")

    if not eof then
        return
    end

    local content_type = ngx.header["Content-Type"]
    if not is_json_response(content_type) then
        ngx.log(ngx.DEBUG, "Body filter - Skipping non-JSON response (Content-Type: " .. tostring(content_type) .. ")")
        return
    end

    local body = ngx.ctx.response_body
    if not is_json_body(body) then
        ngx.log(ngx.WARN, "Body filter - Response is not JSON format. Body preview: " .. tostring(body and body:sub(1, 200)))
        return
    end

    local success, decoded = pcall(cjson.decode, body)
    if not success then
        ngx.log(ngx.ERR, "Body filter - JSON decode error: " .. tostring(decoded))
        return
    end

    if not (decoded and decoded.authToken and decoded.username) then
        ngx.log(ngx.DEBUG, "Body filter - No authToken/username in response, skipping.")
        return
    end

    local dict = ngx.shared.cache
    local username_lower = string.lower(decoded.username)

    local ok, err = dict:set("token:" .. username_lower, decoded.authToken, 7200)
    if not ok then
        ngx.log(ngx.ERR, "Body filter - Error storing token in shared dict: " .. tostring(err))
        return
    end

    local ok_reverse, err_reverse = dict:set("guac_token:" .. decoded.authToken, username_lower, 7200)
    if not ok_reverse then
        ngx.log(ngx.ERR, "Body filter - Error storing reverse token mapping: " .. tostring(err_reverse))
        return
    end

    ngx.log(ngx.INFO, "Body filter - Session token stored for " .. decoded.username)
end

return _M
