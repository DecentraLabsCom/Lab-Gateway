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

    runner.it("propagates a valid demo handoff without creating reservation auth", function()
        local ngx = ngx_factory.new({
            cache = {
                ["demo_session:demo-jti"] = "demo",
                ["demo_exp:demo-jti"] = "500",
            },
            demo_sessions = { ["session:demo-jti"] = "active", occupied = 1 },
            var = { http_cookie = "DEMO_JTI=demo-jti" },
            now = 100,
        })

        handler.run(ngx)

        runner.assert.equals("demo", ngx.req.headers["Authorization"])
        runner.assert.equals(true, ngx.ctx.demo_authenticated)
        runner.assert.equals(nil, ngx.ctx.jwt_authenticated)
        runner.assert.equals(nil, ngx.ctx.jwt_reservation_key)
    end)

    runner.it("keeps a valid reservation JTI working when an unrelated demo cookie is present", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
                ["reservation:jti"] = "0xabc",
            },
            var = { http_cookie = "DEMO_JTI=stale; JTI=jti" },
            now = 100,
        })

        handler.run(ngx)

        runner.assert.equals("dlabs-res-user", ngx.req.headers["Authorization"])
        runner.assert.equals(true, ngx.ctx.jwt_authenticated)
        runner.assert.equals(nil, ngx.ctx.demo_authenticated)
    end)

    runner.it("accepts an authenticated websocket handshake before an upstream session exists", function()
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

        handler.run(ngx)
        runner.assert.equals(nil, ngx.status)
    end)



    runner.it("accepts an authenticated websocket handshake without reservation metadata", function()
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

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("does not require reservation observation for manual websocket sessions", function()
        local ngx = ngx_factory.new({
            var = {
                uri = "/guacamole/websocket-tunnel",
                args = "token=manual-token",
                arg_token = "manual-token",
            },
        })

        handler.run(ngx)
        runner.assert.equals(nil, ngx.status)
    end)
end)

return runner
