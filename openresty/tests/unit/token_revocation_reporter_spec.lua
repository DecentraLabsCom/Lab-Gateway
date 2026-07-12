local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local reporter = require "modules.token_revocation_reporter"

runner.describe("Guacamole token revocation reporter", function()
    runner.it("schedules a durable registration", function()
        local ngx = ngx_factory.new()
        local payload = { authToken = "secret", expiresAt = 500 }
        local removed_path

        local scheduled = reporter.schedule(ngx, payload, {
            persist = function(persisted)
                runner.assert.equals(payload, persisted)
                return true, "/spool/revocation.json"
            end,
            deliver = function(delivered)
                runner.assert.equals(payload, delivered)
                return true
            end,
            remove_persisted = function(path)
                removed_path = path
                return true
            end
        })

        runner.assert.truthy(scheduled)
        runner.assert.equals(1, #ngx._timer_calls.at)
        ngx._timer_calls.at[1].callback(false)
        runner.assert.equals("/spool/revocation.json", removed_path)
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_spool_success"))
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_ingest_success"))
    end)

    runner.it("records a failure after bounded retries", function()
        local ngx = ngx_factory.new()
        local attempts = 0

        reporter.schedule(ngx, { authToken = "secret" }, {
            persist = function()
                return true, "/spool/revocation.json"
            end,
            deliver = function()
                attempts = attempts + 1
                return false, "offline"
            end
        })
        ngx._timer_calls.at[1].callback(false)

        runner.assert.equals(3, attempts)
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_ingest_failure"))
    end)

    runner.it("does not rely on an in-memory timer when the durable spool write fails", function()
        local ngx = ngx_factory.new()
        local scheduled = reporter.schedule(ngx, { authToken = "secret" }, {
            persist = function()
                return false, "disk unavailable"
            end
        })

        runner.assert.equals(false, scheduled)
        runner.assert.equals(0, #ngx._timer_calls.at)
        runner.assert.equals(1, ngx.shared.cache:get("metric:guac_revocation_spool_failure"))
    end)
end)

return runner
