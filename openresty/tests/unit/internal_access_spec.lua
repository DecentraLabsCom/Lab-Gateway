local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_internal_access_path()
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lua/internal_access.lua",
        dir .. "/../lua/internal_access.lua",
        "openresty/lua/internal_access.lua",
        "lua/internal_access.lua"
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate internal_access.lua for tests")
end

local function with_env(env, fn)
    local original_getenv = os.getenv
    env = env or {}
    ---@diagnostic disable-next-line: duplicate-set-field
    os.getenv = function(name)
        local value = env[name]
        if value ~= nil then
            return value
        end
        return original_getenv(name)
    end

    local ok, result = xpcall(fn, debug.traceback)
    os.getenv = original_getenv
    if not ok then
        error(result, 0)
    end
    return result
end

local function run_internal_access(opts)
    local env = opts.env or {}
    local headers = opts.headers or {}
    local ngx = ngx_factory.new({
        var = opts.var or {}
    })

    ngx.req.get_headers = function()
        return headers
    end
    ngx.say = function(message)
        ngx._body = message
    end
    ngx.exit = function(code)
        ngx._exit = code
        return code
    end

    _G.ngx = ngx
    with_env(env, function()
        dofile(resolve_internal_access_path())
    end)
    _G.ngx = nil

    return ngx
end

runner.describe("Access token guard", function()
runner.it("rejects public IPs when no token configured", function()
    local ngx = run_internal_access({
        env = { SECURITY_ACCESS_TOKEN = "" },
        var = { remote_addr = "8.8.8.8" }
    })

    runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
    runner.assert.equals("text/plain", ngx.header["Content-Type"])
end)

runner.it("allows loopback when no token configured", function()
    local ngx = run_internal_access({
        env = { SECURITY_ACCESS_TOKEN = "" },
        var = { remote_addr = "127.0.0.1" }
    })

    runner.assert.equals(nil, ngx.status)
    runner.assert.equals(nil, ngx._exit)
    runner.assert.equals(nil, ngx.req.headers["X-Access-Token"])
end)

    runner.it("rejects when token is invalid", function()
        local ngx = run_internal_access({
            env = { SECURITY_ACCESS_TOKEN = "secret-token" },
            headers = { ["X-Access-Token"] = "wrong-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
        runner.assert.equals("text/plain", ngx.header["Content-Type"])
    end)

    runner.it("allows private network without provided token", function()
        local ngx = run_internal_access({
            env = { SECURITY_ACCESS_TOKEN = "secret-token" },
            var = { remote_addr = "172.17.0.2" }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("secret-token", ngx.req.headers["X-Access-Token"])
    end)

    runner.it("allows valid token on public IP", function()
        local ngx = run_internal_access({
            env = { SECURITY_ACCESS_TOKEN = "secret-token" },
            headers = { ["X-Access-Token"] = "secret-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("secret-token", ngx.req.headers["X-Access-Token"])
    end)

    runner.it("accepts token from cookie", function()
        local ngx = run_internal_access({
            env = { SECURITY_ACCESS_TOKEN = "secret-token" },
            var = {
                remote_addr = "8.8.8.8",
                cookie_access_token = "secret-token"
            }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("secret-token", ngx.req.headers["X-Access-Token"])
    end)
end)

return runner
