local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.fmu_access_handler"

runner.describe("FMU access handler", function()
    runner.it("injects the server-side bearer for a valid HttpOnly session", function()
        local ngx = ngx_factory.new({
            cache = {
                ["fmu_access_token:session-1"] = "technical-jwt",
                ["fmu_access_exp:session-1"] = 500,
            },
            var = { http_cookie = "FMU_SESSION=session-1" },
            now = 100,
        })

        runner.assert.truthy(handler.run(ngx))
        runner.assert.equals("Bearer technical-jwt", ngx.req.headers["Authorization"])
    end)

    runner.it("rehydrates the bearer from durable state after the shared cache is lost", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "FMU_SESSION=session-after-restart" },
            now = 100,
        })
        local store = {
            load = function(_, session_id, now)
                runner.assert.equals("session-after-restart", session_id)
                runner.assert.equals(100, now)
                return "durable-technical-jwt", 500
            end,
        }

        runner.assert.truthy(handler.run(ngx, { store = store }))
        runner.assert.equals("Bearer durable-technical-jwt", ngx.req.headers["Authorization"])
        runner.assert.equals("durable-technical-jwt", ngx.shared.cache:get("fmu_access_token:session-after-restart"))
        runner.assert.equals(400, ngx.shared.cache._ttls["fmu_access_token:session-after-restart"])
    end)

    runner.it("fails closed when durable FMU state cannot be read", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "FMU_SESSION=session-after-restart" },
            now = 100,
        })
        local store = {
            load = function()
                return nil, nil, "durable state unavailable"
            end,
        }

        handler.run(ngx, { store = store })

        runner.assert.equals(ngx.HTTP_SERVICE_UNAVAILABLE, ngx.status)
        runner.assert.equals(ngx.HTTP_SERVICE_UNAVAILABLE, ngx._exit_code)
    end)

    runner.it("rejects an expired FMU session", function()
        local ngx = ngx_factory.new({
            cache = {
                ["fmu_access_token:session-1"] = "technical-jwt",
                ["fmu_access_exp:session-1"] = 100,
            },
            var = { http_cookie = "FMU_SESSION=session-1" },
            now = 100,
        })

        handler.run(ngx)

        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)
end)

return runner
