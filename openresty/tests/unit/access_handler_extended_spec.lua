local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.access_handler"

runner.describe("Access handler one-time cookie policy", function()
    runner.it("never reads a JWT query parameter", function()
        local ngx = ngx_factory.new({
            var = { arg_jwt = "must-not-be-used" }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("rejects a reservation token when its JWT mapping is absent", function()
        local ngx = ngx_factory.new({
            cache = { ["guac_token:reservation-token"] = "dlabs-res-abc" },
            var = { arg_token = "reservation-token" },
            now = 100
        })

        handler.run(ngx)

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("propagates a valid JTI cookie", function()
        local ngx = ngx_factory.new({
            cache = { ["username:jti"] = "alice", ["exp:alice"] = "500" },
            var = { http_cookie = "JTI=jti" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
    end)

    runner.it("persists a reservation websocket observation during access phase", function()
        local reported = false
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
                ["reservation:jti"] = "0xabc",
            },
            var = {
                http_cookie = "JTI=jti",
                uri = "/guacamole/websocket-tunnel",
                args = "token=guac-token",
                arg_token = "guac-token",
            },
            now = 100,
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function(context)
                    runner.assert.equals(ngx, context)
                    reported = true
                    return true
                end,
            },
        })

        runner.assert.truthy(reported)
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("fails a reservation websocket closed when durable observation is unavailable", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
                ["reservation:jti"] = "0xabc",
            },
            var = {
                http_cookie = "JTI=jti",
                uri = "/guacamole/websocket-tunnel",
                args = "token=guac-token",
                arg_token = "guac-token",
            },
            now = 100,
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function()
                    return false, "outbox unavailable"
                end,
            },
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("fails a reservation websocket closed when the reporter raises", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
            },
            var = {
                http_cookie = "JTI=jti",
                uri = "/guacamole/websocket-tunnel",
                args = "token=guac-token",
                arg_token = "guac-token",
            },
            now = 100,
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function()
                    error("unexpected reporter failure")
                end,
            },
        })

        runner.assert.equals(503, ngx.status)
    end)

    runner.it("does not require reservation observation for manual websocket sessions", function()
        local reported = false
        local ngx = ngx_factory.new({
            var = {
                uri = "/guacamole/websocket-tunnel",
                args = "token=manual-token",
                arg_token = "manual-token",
            },
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function()
                    reported = true
                    return false
                end,
            },
        })

        runner.assert.equals(false, reported)
        runner.assert.equals(nil, ngx.status)
    end)
end)

return runner
