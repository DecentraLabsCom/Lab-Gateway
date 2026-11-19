local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.access_handler"
local reservation_connection_signal = require "modules.reservation_connection_signal"

runner.describe("Access handler", function()
    runner.it("removes client supplied Authorization without cookies", function()
        local ngx = ngx_factory.new()
        ngx.req.set_header("Authorization", "guacadmin")
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"], "Client Authorization header must never reach Guacamole")
    end)

    runner.it("falls through silently for unknown JTI (stale cookie)", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "foo=bar; JTI=abc123" }
        })
        ngx.req.set_header("Authorization", "guacadmin")

        handler.run(ngx)
        -- Stale cookie: no Authorization header set, no error status – falls through
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("falls through when expiration is missing", function()
        local cache = { ["username:abc"] = "alice" }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=abc" }
        })
        ngx.req.set_header("Authorization", "guacadmin")

        handler.run(ngx)
        -- Missing exp: falls through silently, no Authorization, no error status
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("falls through for expired sessions", function()
        local cache = {
            ["username:abc"] = "alice",
            ["exp:alice"] = tostring(100)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=abc" },
            now = 200
        })

        handler.run(ngx)
        -- Expired sessions are rejected; a fresh access-code exchange is required.
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("rejects a session exactly at its expiration instant", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:abc"] = "alice",
                ["exp:alice"] = "200"
            },
            var = { http_cookie = "JTI=abc" },
            now = 200
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("sets Authorization header for valid cookies", function()
        local cache = {
            ["username:token123"] = "alice",
            ["exp:alice"] = tostring(500)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "foo=bar; JTI=token123" },
            now = 100
        })

        handler.run(ngx)
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("records a reservation tunnel connect and keeps its disconnect identity", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
                ["reservation:jti"] = "reservation-1",
                ["lab:jti"] = "lab-1",
            },
            var = {
                http_cookie = "JTI=jti",
                http_upgrade = "websocket",
                request_id = "guac-connection-1",
                uri = "/guacamole/websocket-tunnel",
            },
            now = 100,
        })
        local events = {}
        local original_record = reservation_connection_signal.record
        ---@diagnostic disable-next-line: duplicate-set-field
        reservation_connection_signal.record = function(_, payload)
            events[#events + 1] = payload
            return true, { success = true }, 200
        end
        local ok, err = xpcall(function()
            handler.run(ngx)
        end, debug.traceback)
        reservation_connection_signal.record = original_record
        if not ok then error(err, 0) end

        runner.assert.equals(1, #events)
        runner.assert.equals("connected", events[1].event)
        runner.assert.equals("guacamole", events[1].source)
        runner.assert.equals("reservation-1", events[1].reservationId)
        runner.assert.equals("lab-1", events[1].labId)
        runner.assert.equals("guac-connection-1", events[1].connectionId)
        runner.assert.equals("guac-connection-1:1", events[1].eventId)
        runner.assert.equals(1, events[1].sequence)
        runner.assert.equals("guac-connection-1:2", ngx.ctx.reservation_connection.eventId)
    end)

    runner.it("rejects invalid and overlong tunnel request identifiers", function()
        local original_record = reservation_connection_signal.record
        local calls = 0
        ---@diagnostic disable-next-line: duplicate-set-field
        reservation_connection_signal.record = function()
            calls = calls + 1
            return true, { success = true }, 200
        end

        local function run_with_request_id(request_id)
            local ngx = ngx_factory.new({
                cache = {
                    ["username:jti"] = "dlabs-res-user",
                    ["exp:dlabs-res-user"] = "500",
                    ["reservation:jti"] = "reservation-1",
                    ["lab:jti"] = "lab-1",
                },
                var = {
                    http_cookie = "JTI=jti",
                    http_upgrade = "websocket",
                    request_id = request_id,
                    uri = "/guacamole/websocket-tunnel",
                },
                now = 100,
            })
            handler.run(ngx)
            return ngx
        end

        local ok, err = xpcall(function()
            local invalid = run_with_request_id("request id with spaces")
            local overlong = run_with_request_id(string.rep("a", 129))
            runner.assert.equals(ngx_factory.new().HTTP_SERVICE_UNAVAILABLE, invalid.status)
            runner.assert.equals(ngx_factory.new().HTTP_SERVICE_UNAVAILABLE, overlong.status)
            runner.assert.equals(0, calls)
        end, debug.traceback)
        reservation_connection_signal.record = original_record
        if not ok then error(err, 0) end
    end)

    runner.it("fails closed and records a failed lifecycle event when Ops rejects registration", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
                ["reservation:jti"] = "reservation-1",
                ["lab:jti"] = "lab-1",
            },
            var = {
                http_cookie = "JTI=jti",
                http_upgrade = "websocket",
                request_id = "guac-connection-1",
                uri = "/guacamole/websocket-tunnel",
            },
            now = 100,
        })
        local events = {}
        local original_record = reservation_connection_signal.record
        ---@diagnostic disable-next-line: duplicate-set-field
        reservation_connection_signal.record = function(_, payload)
            events[#events + 1] = payload
            return false, "Ops unavailable", ngx.HTTP_SERVICE_UNAVAILABLE
        end
        local ok, err = xpcall(function()
            handler.run(ngx)
        end, debug.traceback)
        reservation_connection_signal.record = original_record
        if not ok then error(err, 0) end

        runner.assert.equals(ngx.HTTP_SERVICE_UNAVAILABLE, ngx.status)
        runner.assert.equals(2, #events)
        runner.assert.equals("connected", events[1].event)
        runner.assert.equals("failed", events[2].event)
        runner.assert.equals("guac-connection-1:2", events[2].eventId)
        runner.assert.equals(nil, ngx.ctx.reservation_connection)
    end)

    runner.it("does not register a reservation lifecycle for a tunnel without reservation metadata", function()
        local ngx = ngx_factory.new({
            cache = {
                ["username:jti"] = "dlabs-res-user",
                ["exp:dlabs-res-user"] = "500",
            },
            var = {
                http_cookie = "JTI=jti",
                http_upgrade = "websocket",
                request_id = "manual-connection-1",
                uri = "/guacamole/websocket-tunnel",
            },
            now = 100,
        })
        local calls = 0
        local original_record = reservation_connection_signal.record
        ---@diagnostic disable-next-line: duplicate-set-field
        reservation_connection_signal.record = function()
            calls = calls + 1
            return true, { success = true }, 200
        end
        local ok, err = xpcall(function()
            handler.run(ngx)
        end, debug.traceback)
        reservation_connection_signal.record = original_record
        if not ok then error(err, 0) end

        runner.assert.equals(0, calls)
        runner.assert.equals(nil, ngx.ctx.reservation_connection)
    end)

    runner.it("does not expire a reservation auth token solely because its tunnel was idle", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:reservation-token"] = "dlabs-res-user",
                ["guac_jwt_exp:reservation-token"] = "500",
                ["guac_jwt_last_seen:reservation-token"] = "100",
            },
            config = { jwt_guac_idle_timeout_seconds = 60 },
            var = { arg_token = "reservation-token" },
            now = 200,
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
    end)
end)

return runner
