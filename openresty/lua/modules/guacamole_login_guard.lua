local _M = {}

local WINDOW_SECONDS = 60
local DEFAULT_LIMIT_PER_MINUTE = 10

local function configured_limit()
    local raw = tonumber(os.getenv("GUACAMOLE_LOGIN_RATE_LIMIT_PER_MINUTE") or "")
    if raw and raw >= 1 and raw <= 1000 then
        return math.floor(raw)
    end
    return DEFAULT_LIMIT_PER_MINUTE
end

local function first_value(value)
    if type(value) == "table" then
        return value[1]
    end
    return value
end

local function reject(ngx, status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Retry-After"] = tostring(WINDOW_SECONDS)
    ngx.say(message)
    return ngx.exit(status)
end

function _M.run(ngx_ctx)
    local ngx = ngx_ctx or ngx
    if ngx.req.get_method() ~= "POST" then
        return
    end

    -- Guacamole's endpoint is application/x-www-form-urlencoded.  Read only
    -- the small form field set needed for the per-user bucket; the body is
    -- still forwarded unchanged to the internal upstream subrequest.
    ngx.req.read_body()
    local args = ngx.req.get_post_args(8) or {}
    local username = first_value(args.username or args.user)
    username = tostring(username or ""):lower():gsub("%s+", " "):sub(1, 128)
    if username == "" then
        username = "<anonymous>"
    end

    local remote_addr = tostring(ngx.var.remote_addr or "unknown")
    local key = "guac-login:" .. remote_addr .. ":" .. username
    local dict = ngx.shared.guac_login_rate
    if not dict then
        return reject(ngx, ngx.HTTP_SERVICE_UNAVAILABLE,
            '{"message":"Login protection is unavailable"}')
    end

    local count, err = dict:incr(key, 1, 0, WINDOW_SECONDS)
    if not count then
        ngx.log(ngx.ERR, "Guacamole login rate counter failed: ", tostring(err))
        return reject(ngx, ngx.HTTP_SERVICE_UNAVAILABLE,
            '{"message":"Login protection is unavailable"}')
    end

    if count > configured_limit() then
        return reject(ngx, ngx.HTTP_TOO_MANY_REQUESTS,
            '{"message":"Too many Guacamole login attempts"}')
    end
end

return _M
