local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local station = require "modules.demo_station"

local function build_ngx(cache)
    return ngx_factory.new({
        now = 100,
        cache = cache or {},
        config = {
            demo_lab_id = "42",
            demo_station_timeout_seconds = 5,
        },
    })
end

local function request_stub(responses)
    local calls = {}
    local deps = {
        request = function(path, payload)
            calls[#calls + 1] = { path = path, payload = payload }
            local response = table.remove(responses, 1)
            if not response then return false, "missing response" end
            return response.ok, response.body or {}
        end,
    }
    return deps, calls
end

runner.describe("Demo Station lifecycle", function()
    runner.it("starts physical preparation with a separate demo operation id", function()
        local ngx = build_ngx()
        local deps, calls = request_stub({ { ok = true, body = { prepared = true } } })

        local started = station.start(ngx, "abc123", 200, deps)

        runner.assert.equals(true, started)
        runner.assert.equals("/api/demo/start", calls[1].path)
        runner.assert.equals("demo:abc123", calls[1].payload.demoId)
        runner.assert.equals("42", calls[1].payload.labId)
        runner.assert.equals("42", ngx.shared.cache:get("demo_operation:abc123"))
    end)

    runner.it("records connection and releases physical preparation idempotently", function()
        local ngx = build_ngx({ ["demo_operation:abc123"] = "42" })
        local deps, calls = request_stub({
            { ok = true, body = {} },
            { ok = true, body = { released = true } },
        })

        runner.assert.equals(true, station.connected(ngx, "abc123", deps))
        runner.assert.equals(true, station.finish(ngx, "abc123", "expired", deps))
        runner.assert.equals("/api/demo/event", calls[1].path)
        runner.assert.equals("connected", calls[1].payload.event)
        runner.assert.equals("/api/demo/end", calls[2].path)
        runner.assert.equals("expired", calls[2].payload.reason)
        runner.assert.equals(nil, ngx.shared.cache:get("demo_operation:abc123"))
        runner.assert.equals("expired", ngx.shared.cache:get("demo_ended:abc123"))
        runner.assert.equals(true, station.finish(ngx, "abc123", "expired", deps))
        runner.assert.equals(2, #calls)
    end)

    runner.it("fails closed when physical preparation cannot be confirmed", function()
        local ngx = build_ngx()
        local deps, calls = request_stub({
            { ok = false, body = { error = "prepare failed" } },
            { ok = true, body = { released = true } },
        })

        runner.assert.equals(false, station.start(ngx, "failed", 200, deps))
        runner.assert.equals("/api/demo/end", calls[2].path)
        runner.assert.equals(nil, ngx.shared.cache:get("demo_operation:failed"))
    end)

    runner.it("keeps failed cleanup retryable until Ops confirms release", function()
        local ngx = build_ngx({ ["demo_operation:retry"] = "42" })
        local deps, calls = request_stub({
            { ok = false, body = { error = "station unavailable" } },
            { ok = true, body = { released = true } },
        })

        runner.assert.equals(false, station.finish(ngx, "retry", "disconnected", deps))
        runner.assert.equals("disconnected", ngx.shared.cache:get("demo_cleanup_pending:retry"))
        runner.assert.equals(true, station.finish(ngx, "retry", "disconnected", deps))
        runner.assert.equals(nil, ngx.shared.cache:get("demo_cleanup_pending:retry"))
        runner.assert.equals(nil, ngx.shared.cache:get("demo_operation:retry"))
        runner.assert.equals(2, #calls)
    end)
end)

return runner
