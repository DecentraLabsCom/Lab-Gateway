local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.log_handler"

local function base_env(overrides)
    overrides = overrides or {}
    local env = {
        var = {
            uri = "/guacamole/websocket-tunnel",
            status = "204",
            args = overrides.args,
            http_authorization = overrides.authorization
        },
        cache = overrides.cache or {},
        config = overrides.config or {
            auto_logout_on_disconnect = true,
            admin_user = "guacadmin"
        },
        now = overrides.now or 100
    }
    return ngx_factory.new(env)
end

runner.describe("Log handler", function()
    runner.it("ignores non websocket requests", function()
        local ngx = base_env()
        ngx.var.uri = "/health"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("ignores active connections", function()
        local ngx = base_env()
        ngx.var.status = "101"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("skips when auto logout disabled", function()
        local ngx = base_env({
            config = {
                auto_logout_on_disconnect = false,
                admin_user = "guacadmin"
            }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("skips admin user", function()
        local ngx = base_env({ authorization = "guacadmin" })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("skips JWT managed users", function()
        local ngx = base_env({
            authorization = "alice",
            cache = { ["exp:alice"] = 999 }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["pending_user:alice"])
    end)

    runner.it("marks manual sessions via token lookup", function()
        local ngx = base_env({
            args = "token=abc123",
            cache = { ["guac_token:abc123"] = "Alice" },
            now = 200
        })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:alice"])
        runner.assert.truthy(cache["tunnel_closed:alice"])
        runner.assert.truthy(cache["has_pending_closures"])
    end)

    runner.it("logs when username missing and skips", function()
        local ngx = base_env({
            args = nil,
            authorization = nil
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("uses Authorization header when present", function()
        local ngx = base_env({ authorization = "ManualUser" })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:manualuser"])
    end)
end)

return runner
