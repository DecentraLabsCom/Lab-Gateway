local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_admin_access_path()
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lua/admin_access.lua",
        dir .. "/../lua/admin_access.lua",
        "openresty/lua/admin_access.lua",
        "lua/admin_access.lua"
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate admin_access.lua for tests")
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

local function run_admin_access(opts)
    local env = opts.env or {}
    local headers = opts.headers or {}
    local uri_args = opts.uri_args or {}
    local ngx = ngx_factory.new({
        var = opts.var or {}
    })

    ngx.req.get_headers = function()
        return headers
    end
    ngx.req.get_uri_args = function()
        return uri_args
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
        dofile(resolve_admin_access_path())
    end)
    _G.ngx = nil

    return ngx
end

runner.describe("Treasury admin token guard", function()
    runner.it("rejects public IPs when TREASURY_TOKEN is not configured", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
    end)

    runner.it("allows loopback when TREASURY_TOKEN is not configured", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "" },
            var = { remote_addr = "127.0.0.1" }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals(nil, ngx._exit)
    end)

    runner.it("rejects invalid TREASURY_TOKEN on public IP", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "treasury-token" },
            headers = { ["X-Access-Token"] = "wrong-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
    end)

    runner.it("requires token on private network when TREASURY_TOKEN is configured", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "treasury-token" },
            var = { remote_addr = "172.17.0.2" }
        })

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
    end)

    runner.it("allows valid TREASURY_TOKEN on public IP", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "treasury-token" },
            headers = { ["X-Access-Token"] = "treasury-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("treasury-token", ngx.req.headers["X-Access-Token"])
    end)

    runner.it("does not accept LAB_MANAGER_TOKEN header for treasury admin access", function()
        local ngx = run_admin_access({
            env = {
                TREASURY_TOKEN = "treasury-token",
                LAB_MANAGER_TOKEN = "lab-token"
            },
            headers = { ["X-Lab-Manager-Token"] = "lab-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx._exit)
    end)

    runner.it("accepts token from query parameter and sets access cookie", function()
        local ngx = run_admin_access({
            env = { TREASURY_TOKEN = "treasury-token" },
            uri_args = { token = "treasury-token" },
            var = { remote_addr = "8.8.8.8" }
        })

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("treasury-token", ngx.req.headers["X-Access-Token"])
        runner.assert.equals("access_token=treasury-token; Path=/; HttpOnly; Secure; SameSite=Lax", ngx.header["Set-Cookie"])
    end)
end)

return runner
