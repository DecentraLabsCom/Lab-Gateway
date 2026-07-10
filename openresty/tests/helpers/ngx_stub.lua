local function new_shared_dict(initial)
    local store = {}
    if initial then
        for k, v in pairs(initial) do
            store[k] = v
        end
    end

    local dict = {}

    function dict:get(key)
        return store[key]
    end

    function dict:set(key, value, ttl)
        store[key] = value
        dict._ttls[key] = ttl
        return true
    end

    function dict:delete(key)
        store[key] = nil
    end

    function dict:get_keys()
        local keys = {}
        for key in pairs(store) do
            keys[#keys + 1] = key
        end
        return keys
    end

    function dict:incr(key, amount, default, _ttl)
        local current = store[key]
        if current == nil then
            if default == nil then
                return nil, "not found"
            end
            current = default
        end
        store[key] = current + amount
        return store[key], nil
    end

    dict._data = store
    dict._ttls = {}
    return dict
end

local function new(opts)
    opts = opts or {}
    local logs = {}
    local req_headers = {}
    local now = opts.now or 0

    local timer_calls = {
        at = {},
        every = {}
    }

    local ngx_stub = {
        DEBUG = "DEBUG",
        INFO = "INFO",
        WARN = "WARN",
        ERR = "ERR",
        HTTP_UNAUTHORIZED = 401,
        HTTP_SERVICE_UNAVAILABLE = 503,
        HTTP_TOO_MANY_REQUESTS = 429,
        status = opts.status or nil,
        header = opts.header or {},
        var = opts.var or {},
        http = opts.http or {},
        shared = {
            cache         = opts.cache_dict         or new_shared_dict(opts.cache         or {}),
            config        = opts.config_dict        or new_shared_dict(opts.config        or {}),
            demo_sessions = opts.demo_sessions_dict or new_shared_dict(opts.demo_sessions or {})
        },
        req = {},
        ctx = opts.ctx or {},
        timer = {}
    }

    function ngx_stub.time()
        return now
    end

    function ngx_stub.set_now(value)
        now = value
    end

    function ngx_stub.req.set_header(key, value)
        req_headers[key] = value
    end

    function ngx_stub.req.clear_header(key)
        req_headers[key] = nil
    end

    function ngx_stub.req.get_headers()
        return req_headers
    end

    ngx_stub.req.headers = req_headers

    function ngx_stub.log(_, level, message)
        logs[#logs + 1] = { level = level, message = tostring(message) }
    end

    ngx_stub._logs = logs

    function ngx_stub.timer.at(delay, callback)
        timer_calls.at[#timer_calls.at + 1] = { delay = delay, callback = callback }
        return true
    end

    function ngx_stub.timer.every(interval, callback)
        timer_calls.every[#timer_calls.every + 1] = { interval = interval, callback = callback }
        return true
    end

    ngx_stub._timer_calls = timer_calls

    local say_output = {}
    function ngx_stub.say(msg)
        say_output[#say_output + 1] = tostring(msg)
    end
    ngx_stub._say_output = say_output

    function ngx_stub.exit(code)
        ngx_stub._exit_code = code
    end

    function ngx_stub.escape_uri(s)
        return tostring(s)
    end

    return ngx_stub
end

return {
    new = new,
    new_shared_dict = new_shared_dict
}
