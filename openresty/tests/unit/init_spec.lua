local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_lua_path(name)
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lua/" .. name,
        dir .. "/../lua/" .. name,
        "openresty/lua/" .. name,
        "lua/" .. name
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate " .. name .. " for tests")
end

local INIT_LUA_PATH = resolve_lua_path("init.lua")

local function with_overrides(opts, fn)
    local previous_getenv = os.getenv
    local previous_open = io.open
    local previous_ngx = _G.ngx
    local env = opts.env or {}
    local files = opts.files or {}

    ---@diagnostic disable-next-line: duplicate-set-field
    os.getenv = function(name)
        return env[name]
    end

    io.open = function(path, mode)
        local content = files[path]
        if content == nil then
            return nil
        end

        return {
            read = function(_, pattern)
                return content
            end,
            close = function() end
        }
    end

    _G.ngx = opts.ngx

    local ok, result = xpcall(fn, debug.traceback)

    _G.ngx = previous_ngx
    os.getenv = previous_getenv
    io.open = previous_open

    if not ok then
        error(result, 0)
    end

    return result
end

local function run_init(opts)
    local ngx = opts.ngx or ngx_factory.new()
    with_overrides({
        env = opts.env,
        files = opts.files,
        ngx = ngx
    }, function()
        dofile(INIT_LUA_PATH)
    end)
    return ngx
end

runner.describe("OpenResty init.lua", function()
    runner.it("stores shared configuration and public key for full mode", function()
        local public_key = "-----BEGIN PUBLIC KEY-----\nabc123\n-----END PUBLIC KEY-----"
        local ngx = run_init({
            env = {
                GUAC_ADMIN_USER = "admin",
                GUAC_ADMIN_PASS = "really-strong-secret",
                SERVER_NAME = "gateway.example",
                HTTPS_PORT = "8443",
                AUTO_LOGOUT_ON_DISCONNECT = "true"
            },
            files = {
                ["/etc/ssl/private/public_key.pem"] = public_key
            }
        })

        runner.assert.equals("gateway.example", ngx.shared.config:get("server_name"))
        runner.assert.equals("/guacamole", ngx.shared.config:get("guac_uri"))
        runner.assert.equals("https://gateway.example:8443/auth", ngx.shared.config:get("issuer"))
        runner.assert.equals(0, ngx.shared.config:get("lite_mode"))
        runner.assert.equals("admin", ngx.shared.config:get("admin_user"))
        runner.assert.equals("really-strong-secret", ngx.shared.config:get("admin_pass"))
        runner.assert.equals("8443", ngx.shared.config:get("https_port"))
        runner.assert.equals(true, ngx.shared.config:get("auto_logout_on_disconnect"))
        runner.assert.equals("http://guacamole:8080/guacamole/api", ngx.shared.config:get("guac_api_url"))
        runner.assert.equals(public_key, ngx.shared.cache:get("public_key"))
    end)

    runner.it("enables lite mode when ISSUER points to an external origin", function()
        local ngx = run_init({
            env = {
                GUAC_ADMIN_USER = "admin",
                GUAC_ADMIN_PASS = "really-strong-secret",
                SERVER_NAME = "gateway.example",
                HTTPS_PORT = "443",
                ISSUER = "https://issuer.example/auth/",
                GUAC_API_URL = "http://guac.internal/guacamole/api"
            },
            files = {
                ["/etc/ssl/private/public_key.pem"] = "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----"
            }
        })

        runner.assert.equals(1, ngx.shared.config:get("lite_mode"))
        runner.assert.equals("https://issuer.example/auth/", ngx.shared.config:get("issuer"))
        runner.assert.equals("http://guac.internal/guacamole/api", ngx.shared.config:get("guac_api_url"))
    end)

    runner.it("fails fast when required variables are missing", function()
        local ok, err = pcall(function()
            run_init({
                env = {
                    GUAC_ADMIN_PASS = "really-strong-secret"
                },
                files = {}
            })
        end)

        runner.assert.equals(false, ok)
        runner.assert.truthy(tostring(err):find("missing required env var: GUAC_ADMIN_USER", 1, true) ~= nil)
    end)

    runner.it("refuses the default Guacamole admin password", function()
        local ok, err = pcall(function()
            run_init({
                env = {
                    GUAC_ADMIN_USER = "admin",
                    GUAC_ADMIN_PASS = "guacadmin"
                },
                files = {}
            })
        end)

        runner.assert.equals(false, ok)
        runner.assert.truthy(tostring(err):find("refusing default value for GUAC_ADMIN_PASS", 1, true) ~= nil)
    end)
end)

return runner
