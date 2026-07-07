local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local reporter = require "modules.access_audit_reporter"
local cjson = require "cjson.safe"

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

local function http_factory(calls, status)
    return function()
        return {
            request_uri = function(_, url, request)
                calls[#calls + 1] = { url = url, request = request }
                return { status = status or 200, body = '{"recorded":true}' }, nil
            end
        }
    end
end

runner.describe("Access audit reporter", function()
    runner.it("posts Guacamole session observation with hashed session id", function()
        local calls = {}
        local ngx = new_ngx()

        local scheduled = reporter.report_guacamole_session_observed(ngx, {
            access_token = "internal-token",
            cjson = cjson,
            http_factory = http_factory(calls),
            sha256_hex = function(value)
                runner.assert.equals("guac-token", value)
                return "abc123"
            end,
            audit_url = "http://backend/access-audit/internal/session-observed",
            gateway_id = "gateway-a"
        })

        runner.assert.truthy(scheduled)
        runner.assert.equals(1, #ngx._timer_calls.at)
        ngx._timer_calls.at[1].callback(false)

        runner.assert.equals(1, #calls)
        runner.assert.equals("http://backend/access-audit/internal/session-observed", calls[1].url)
        runner.assert.equals("internal-token", calls[1].request.headers["X-Access-Token"])

        local payload = cjson.decode(calls[1].request.body)
        runner.assert.equals("0xabc", payload.reservationKey)
        runner.assert.equals("jwt-jti", payload.jwtJti)
        runner.assert.equals("guac:abc123", payload.sessionId)
        runner.assert.equals("gateway-a", payload.gatewayId)
        runner.assert.equals("guacamole", payload.accessType)
        runner.assert.equals(1234, payload.observedAt)
    end)

    runner.it("does not report the same Guacamole token twice", function()
        local calls = {}
        local ngx = new_ngx()
        local deps = {
            access_token = "internal-token",
            cjson = cjson,
            http_factory = http_factory(calls),
            sha256_hex = function()
                return "abc123"
            end
        }

        reporter.report_guacamole_session_observed(ngx, deps)
        reporter.report_guacamole_session_observed(ngx, deps)

        runner.assert.equals(1, #ngx._timer_calls.at)
    end)

    runner.it("skips when reservation metadata is missing", function()
        local calls = {}
        local ngx = new_ngx({ cache = {} })

        local scheduled = reporter.report_guacamole_session_observed(ngx, {
            access_token = "internal-token",
            cjson = cjson,
            http_factory = http_factory(calls),
            sha256_hex = function()
                return "abc123"
            end
        })

        runner.assert.equals(false, scheduled)
        runner.assert.equals(0, #calls)
    end)
end)

return runner
