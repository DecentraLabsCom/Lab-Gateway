local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local cjson = require "cjson.safe"

local function with_environment(values, callback)
    local previous_getenv = os.getenv
    os.getenv = function(name) return values[name] end
    local ok, result = xpcall(callback, debug.traceback)
    os.getenv = previous_getenv
    if not ok then error(result, 0) end
    return result
end

local function with_http_stub(http_stub, callback)
    local previous_loaded = package.loaded["resty.http"]
    local previous_preload = package.preload["resty.http"]
    local previous_signal = package.loaded["modules.reservation_connection_signal"]
    package.loaded["resty.http"] = nil
    package.preload["resty.http"] = function() return http_stub end
    package.loaded["modules.reservation_connection_signal"] = nil

    local ok, result = xpcall(callback, debug.traceback)

    package.loaded["resty.http"] = previous_loaded
    package.preload["resty.http"] = previous_preload
    package.loaded["modules.reservation_connection_signal"] = previous_signal
    if not ok then error(result, 0) end
    return result
end

runner.describe("reservation connection signal", function()
    runner.it("posts the lifecycle event with internal authentication", function()
        local captured = {}
        local http_stub = {
            new = function()
                local client = {}
                function client:set_timeout(timeout) captured.timeout = timeout end
                function client:request_uri(url, request)
                    captured.url = url
                    captured.request = request
                    return { status = 200, body = '{"success":true,"state":"grace"}' }
                end
                function client:set_keepalive(timeout, pool_size)
                    captured.keepalive = { timeout, pool_size }
                end
                return client
            end
        }
        local payload = {
            reservationId = "reservation-1",
            labId = "lab-1",
            source = "guacamole",
            connectionId = "connection-1",
            eventId = "connection-1:2",
            event = "disconnected",
            sequence = 2
        }
        local ngx = ngx_factory.new({ config = { ops_api_url = "http://ops.internal/" } })

        with_environment({
            OPS_INTERNAL_AUTH_TOKEN = "internal-token",
            OPS_INTERNAL_AUTH_HEADER = "X-Ops-Token"
        }, function()
            with_http_stub(http_stub, function()
                local signal = require "modules.reservation_connection_signal"
                local ok, result, status = signal.record(ngx, payload)

                runner.assert.equals(true, ok)
                runner.assert.equals(200, status)
                runner.assert.equals(true, result.success)
            end)
        end)

        runner.assert.equals(1500, captured.timeout)
        runner.assert.equals("http://ops.internal/api/reservation-connections/event", captured.url)
        runner.assert.equals("POST", captured.request.method)
        runner.assert.equals("internal-token", captured.request.headers["X-Ops-Token"])
        runner.assert.equals("application/json", captured.request.headers["Content-Type"])
        runner.assert.equals("reservation-1", cjson.decode(captured.request.body).reservationId)
        runner.assert.equals(10000, captured.keepalive[1])
        runner.assert.equals(5, captured.keepalive[2])
    end)

    runner.it("fails closed when the internal token is missing", function()
        local calls = 0
        local http_stub = {
            new = function()
                calls = calls + 1
                return {}
            end
        }
        with_environment({}, function()
            with_http_stub(http_stub, function()
                local signal = require "modules.reservation_connection_signal"
                local ok, message, status = signal.record(ngx_factory.new(), {})

                runner.assert.equals(false, ok)
                runner.assert.equals(503, status)
                runner.assert.truthy(tostring(message):find("authentication", 1, true))
            end)
        end)
        runner.assert.equals(0, calls)
    end)

    runner.it("preserves Ops rejection instead of acknowledging an unrecorded event", function()
        local http_stub = {
            new = function()
                local client = {}
                function client:set_timeout() end
                function client:request_uri()
                    return { status = 409, body = '{"success":false,"error":"stale event"}' }
                end
                return client
            end
        }
        with_environment({ OPS_INTERNAL_AUTH_TOKEN = "internal-token" }, function()
            with_http_stub(http_stub, function()
                local signal = require "modules.reservation_connection_signal"
                local ok, message, status = signal.record(ngx_factory.new(), {})

                runner.assert.equals(false, ok)
                runner.assert.equals(409, status)
                runner.assert.equals("stale event", message)
            end)
        end)
    end)
end)
