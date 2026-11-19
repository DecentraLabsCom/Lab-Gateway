local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.log_handler"
local reservation_connection_signal = require "modules.reservation_connection_signal"

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
        demo_sessions = overrides.demo_sessions or {},
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

    runner.it("does not queue closure while a websocket is active", function()
        local ngx = base_env()
        ngx.var.status = "101"
        handler.run(ngx)
        runner.assert.equals(nil, ngx.shared.cache._data["has_pending_closures"])
    end)

    runner.it("records the reservation disconnect when the Guacamole tunnel closes", function()
        local ngx = base_env()
        ngx.var.status = "101"
        ngx.ctx.reservation_connection = {
            reservationId = "reservation-1",
            labId = "lab-1",
            source = "guacamole",
            connectionId = "guac-connection-1",
            eventId = "guac-connection-1:2",
            sequence = 2,
        }
        local captured
        local original_record = reservation_connection_signal.record
        ---@diagnostic disable-next-line: duplicate-set-field
        reservation_connection_signal.record = function(_, payload)
            captured = payload
            return true, { success = true }, 200
        end
        local ok, err = xpcall(function()
            handler.run(ngx)
            runner.assert.equals(1, #ngx._timer_calls.at)
            ngx._timer_calls.at[1].callback(true)
            runner.assert.equals(nil, captured, "premature timer must not report a disconnect")
            ngx._timer_calls.at[1].callback(false)
        end, debug.traceback)
        reservation_connection_signal.record = original_record
        if not ok then error(err, 0) end

        runner.assert.equals("disconnected", captured.event)
        runner.assert.equals("guacamole", captured.source)
        runner.assert.equals("reservation-1", captured.reservationId)
        runner.assert.equals("lab-1", captured.labId)
        runner.assert.equals("guac-connection-1", captured.connectionId)
        runner.assert.equals("guac-connection-1:2", captured.eventId)
        runner.assert.equals(2, captured.sequence)
    end)

    runner.it("releases the physical demo lifecycle when the tunnel closes", function()
        local ngx = base_env({
            demo_sessions = { occupied = 1, ["session:demo-jti"] = "active" },
        })
        ngx.var.status = "101"
        ngx.ctx.demo_session_jti = "demo-jti"
        local released = false

        handler.run(ngx, {
            demo_station = {
                finish = function(_, jti, reason)
                    released = jti == "demo-jti" and reason == "disconnected"
                    return true
                end,
            },
        })
        ngx._timer_calls.at[1].callback(false)

        runner.assert.equals(true, released)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("session:demo-jti"))
        runner.assert.equals(0, ngx.shared.demo_sessions:get("occupied"))
    end)

    runner.it("releases the gateway slot even when physical close needs a retry", function()
        local ngx = base_env({
            demo_sessions = { occupied = 1, ["session:demo-jti"] = "active" },
        })
        ngx.var.status = "101"
        ngx.ctx.demo_session_jti = "demo-jti"

        handler.run(ngx, {
            demo_station = {
                finish = function() return false, "station unavailable" end,
            },
        })
        ngx._timer_calls.at[1].callback(false)

        runner.assert.equals(nil, ngx.shared.demo_sessions:get("session:demo-jti"))
        runner.assert.equals(0, ngx.shared.demo_sessions:get("occupied"))
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

    runner.it("keeps expired JWT users out of manual-session cleanup during enforcement retention", function()
        local ngx = base_env({
            authorization = "alice",
            cache = { ["guac_enforcement_exp:alice"] = 99 }
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
        ngx.var.status = "101"
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
