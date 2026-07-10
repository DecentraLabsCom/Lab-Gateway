local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local reporter = require "modules.access_audit_reporter"

local function new_ngx(opts)
    opts = opts or {}
    return ngx_factory.new({
        var = {
            args = opts.args or "token=guac-token"
        },
        cache = opts.cache or {
            ["guac_reservation:guac-token"] = "0xabc",
            ["guac_jti:guac-token"] = "jwt-jti"
        },
        config = opts.config or {
            server_name = "gateway-a"
        },
        now = opts.now or 1234
    })
end

runner.describe("Access audit reporter", function()
    runner.it("schedules Guacamole session observation outside the header filter phase", function()
        local payloads = {}
        local ngx = new_ngx()

        local persisted = reporter.report_guacamole_session_observed(ngx, {
            schedule = function(payload)
                payloads[#payloads + 1] = payload
                return true
            end,
            sha256_hex = function(value)
                runner.assert.equals("guac-token", value)
                return "abc123"
            end
        })

        runner.assert.truthy(persisted)
        runner.assert.equals(1, #payloads)
        local payload = payloads[1]
        runner.assert.equals("0xabc", payload.reservationKey)
        runner.assert.equals("jwt-jti", payload.jwtJti)
        runner.assert.equals("guac:abc123", payload.sessionId)
        runner.assert.equals("gateway-a", payload.gatewayId)
        runner.assert.equals("guacamole", payload.accessType)
        runner.assert.equals(1234, payload.observedAt)
    end)

    runner.it("keeps a stable deduplication key for repeated websocket signals", function()
        local payloads = {}
        local ngx = new_ngx()
        local deps = {
            schedule = function(payload)
                payloads[#payloads + 1] = payload
                return true
            end,
            sha256_hex = function()
                return "abc123"
            end
        }

        reporter.report_guacamole_session_observed(ngx, deps)
        reporter.report_guacamole_session_observed(ngx, deps)

        runner.assert.equals(2, #payloads)
        runner.assert.equals(payloads[1].dedupKey, payloads[2].dedupKey)
    end)

    runner.it("skips when reservation metadata is missing", function()
        local payloads = {}
        local ngx = new_ngx({ cache = {} })

        local scheduled = reporter.report_guacamole_session_observed(ngx, {
            schedule = function(payload)
                payloads[#payloads + 1] = payload
                return true
            end,
            sha256_hex = function()
                return "abc123"
            end
        })

        runner.assert.equals(false, scheduled)
        runner.assert.equals(0, #payloads)
    end)
end)

return runner
