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
