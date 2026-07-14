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
    runner.it("durably ingests the Guacamole observation before accepting the websocket", function()
        local payloads = {}
        local ngx = new_ngx()

        local persisted = reporter.report_guacamole_session_observed(ngx, {
            deliver = function(payload)
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
        runner.assert.equals(1234, payload.reportedAt)
    end)

    runner.it("keeps a stable deduplication key for repeated websocket signals", function()
        local payloads = {}
        local ngx = new_ngx()
        local deps = {
            deliver = function(payload)
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

    runner.it("computes SHA-256 with the installed OpenSSL module when ngx has no helper", function()
        local payload
        local persisted = reporter.report_guacamole_session_observed(new_ngx(), {
            deliver = function(value)
                payload = value
                return true
            end,
        })

        runner.assert.truthy(persisted)
        runner.assert.equals(64, #payload.dedupKey)
        runner.assert.truthy(payload.dedupKey:match("^[0-9a-f]+$"))
    end)

    runner.it("skips when reservation metadata is missing", function()
        local payloads = {}
        local ngx = new_ngx({ cache = {} })

        local persisted = reporter.report_guacamole_session_observed(ngx, {
            deliver = function(payload)
                payloads[#payloads + 1] = payload
                return true
            end,
            sha256_hex = function()
                return "abc123"
            end
        })

        runner.assert.equals(false, persisted)
        runner.assert.equals(0, #payloads)
    end)

    runner.it("fails closed when the durable ingest endpoint is unavailable", function()
        local ngx = new_ngx()

        local persisted = reporter.report_guacamole_session_observed(ngx, {
            deliver = function()
                return false, "database unavailable"
            end,
            sha256_hex = function()
                return "abc123"
            end
        })

        runner.assert.equals(false, persisted)
        runner.assert.equals(1, ngx.shared.cache:get("metric:session_observation_ingest_failure"))
    end)
end)

return runner
