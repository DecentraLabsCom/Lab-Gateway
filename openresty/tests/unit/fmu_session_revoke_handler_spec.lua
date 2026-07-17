local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.fmu_session_revoke_handler"

runner.describe("FMU session revocation handler", function()
    runner.it("deletes the server-side FMU ticket mappings", function()
        local ngx = ngx_factory.new({
            method = "POST",
            cache = {
                ["fmu_access_token:session-123456789"] = "technical-jwt",
                ["fmu_access_exp:session-123456789"] = 500,
            },
            var = { http_cookie = "FMU_SESSION=session-123456789" },
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.shared.cache:get("fmu_access_token:session-123456789"))
        runner.assert.equals(nil, ngx.shared.cache:get("fmu_access_exp:session-123456789"))
        runner.assert.equals(204, ngx._exit_code)
    end)

    runner.it("is idempotent when the browser no longer has the ticket cookie", function()
        local ngx = ngx_factory.new({ method = "POST" })

        handler.run(ngx)

        runner.assert.equals(204, ngx._exit_code)
    end)
end)

return runner
