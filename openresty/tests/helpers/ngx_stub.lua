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

    function dict:set(key, value)
        store[key] = value
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

    dict._data = store
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
        status = nil,
        header = opts.header or {},
        var = opts.var or {},
        shared = {
            cache = opts.cache_dict or new_shared_dict(opts.cache or {}),
            config = opts.config_dict or new_shared_dict(opts.config or {})
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

    return ngx_stub
end

return {
    new = new,
    new_shared_dict = new_shared_dict
}
