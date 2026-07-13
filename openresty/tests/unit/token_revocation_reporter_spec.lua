local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local reporter = require "modules.token_revocation_reporter"

runner.describe("Guacamole token revocation reporter", function()
    runner.it("returns only after the encrypted queue accepts registration", function()
        local ngx = ngx_factory.new()
        local payload = { authToken = "secret", expiresAt = 500 }
        local calls = 0

        local registered = reporter.register(ngx, payload, {
            deliver = function(delivered)
                runner.assert.equals(payload, delivered)
                calls = calls + 1
                return true
            end,
        })

        runner.assert.truthy(registered)
        runner.assert.equals(1, calls)
        runner.assert.equals(0, #ngx._timer_calls.at)
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_ingest_success"))
    end)

    runner.it("fails closed immediately when durable registration is unavailable", function()
        local ngx = ngx_factory.new()
        local registered = reporter.register(ngx, { authToken = "secret" }, {
            deliver = function()
                return false, "offline"
            end,
        })

        runner.assert.equals(false, registered)
        runner.assert.equals(0, #ngx._timer_calls.at)
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_ingest_failure"))
    end)
end)

return runner
