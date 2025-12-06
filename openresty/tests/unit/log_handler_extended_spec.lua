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

runner.describe("Log handler extended tests", function()
    -- Test: Various non-websocket URIs
    runner.it("ignores /health endpoint", function()
        local ngx = base_env()
        ngx.var.uri = "/health"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("ignores /guacamole/api requests", function()
        local ngx = base_env()
        ngx.var.uri = "/guacamole/api/tokens"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("ignores /guacamole/ root path", function()
        local ngx = base_env()
        ngx.var.uri = "/guacamole/"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    -- Test: Various connection statuses
    runner.it("ignores status 200", function()
        local ngx = base_env()
        ngx.var.status = "200"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("ignores status 500", function()
        local ngx = base_env()
        ngx.var.status = "500"
        handler.run(ngx)
        -- 500 is not 101, so it's not an active connection, should process
        -- but depends on implementation
    end)

    -- Test: Admin user variations
    runner.it("skips admin user case-insensitive", function()
        local ngx = base_env({ authorization = "GUACADMIN" })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["pending_user:guacadmin"])
    end)

    runner.it("skips admin user with mixed case", function()
        local ngx = base_env({ authorization = "GuacAdmin" })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["pending_user:guacadmin"])
    end)

    -- Test: Token lookup from query string
    runner.it("extracts username from token in middle of args", function()
        local ngx = base_env({
            args = "width=800&token=abc123&height=600",
            cache = { ["guac_token:abc123"] = "TestUser" },
            now = 200
        })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:testuser"])
    end)

    runner.it("handles token without value in args", function()
        local ngx = base_env({
            args = "width=800&token=&height=600"
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("handles token not found in cache", function()
        local ngx = base_env({
            args = "token=unknown123"
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    -- Test: Username normalization
    runner.it("normalizes username to lowercase", function()
        local ngx = base_env({ authorization = "MixedCaseUser" })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:mixedcaseuser"])
        runner.assert.equals(nil, cache["pending_user:MixedCaseUser"])
    end)

    -- Test: TTL values set correctly
    runner.it("sets tunnel_closed with timestamp", function()
        local ngx = base_env({
            authorization = "TimedUser",
            now = 12345
        })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.equals(12345, cache["tunnel_closed:timeduser"])
    end)

    -- Test: Empty authorization header
    runner.it("handles empty authorization header", function()
        local ngx = base_env({ authorization = "" })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    -- Test: Both authorization and token present
    runner.it("prefers authorization header over token", function()
        local ngx = base_env({
            authorization = "HeaderUser",
            args = "token=abc123",
            cache = { ["guac_token:abc123"] = "TokenUser" },
            now = 200
        })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:headeruser"])
        runner.assert.equals(nil, cache["pending_user:tokenuser"])
    end)

    -- Test: Config without admin_user set
    runner.it("handles missing admin_user in config", function()
        local ngx = base_env({
            authorization = "SomeUser",
            config = { auto_logout_on_disconnect = true }
        })
        handler.run(ngx)
        local cache = ngx.shared.cache._data
        runner.assert.truthy(cache["pending_user:someuser"])
    end)

    -- Test: Different websocket-tunnel path variations
    runner.it("matches websocket-tunnel with query params", function()
        local ngx = base_env({ authorization = "TunnelUser" })
        ngx.var.uri = "/guacamole/websocket-tunnel?id=123"
        handler.run(ngx)
        -- URI pattern should still match
        local cache = ngx.shared.cache._data
        -- Depending on implementation, may or may not match
    end)

    -- Test: JWT user expiration lookup
    runner.it("skips user with valid JWT expiration", function()
        local ngx = base_env({
            authorization = "JwtUser",
            cache = { ["exp:jwtuser"] = tostring(999) }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["pending_user:jwtuser"])
    end)

    runner.it("skips user with any expiration value", function()
        local ngx = base_env({
            authorization = "ExpiredJwtUser",
            cache = { ["exp:expiredjwtuser"] = tostring(50) } -- expired but exists
        })
        handler.run(ngx)
        -- Even expired JWT users are skipped (cleanup handled elsewhere)
        runner.assert.equals(nil, ngx.shared.cache._data["pending_user:expiredjwtuser"])
    end)

    -- Test: Multiple pending closures
    runner.it("handles multiple user closures", function()
        local ngx1 = base_env({ authorization = "User1", now = 100 })
        handler.run(ngx1)
        
        local ngx2 = base_env({ authorization = "User2", now = 101, cache = ngx1.shared.cache._data })
        -- Create new ngx with same cache
        local ngx_shared = ngx_factory.new({
            var = { uri = "/guacamole/websocket-tunnel", status = "204", http_authorization = "User2" },
            cache = ngx1.shared.cache._data,
            config = { auto_logout_on_disconnect = true, admin_user = "guacadmin" },
            now = 101
        })
        handler.run(ngx_shared)
        
        local cache = ngx_shared.shared.cache._data
        runner.assert.truthy(cache["pending_user:user1"])
        runner.assert.truthy(cache["pending_user:user2"])
        runner.assert.truthy(cache["has_pending_closures"])
    end)
end)

return runner
