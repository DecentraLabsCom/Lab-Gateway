local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.access_handler"

runner.describe("Access handler one-time cookie policy", function()
    runner.it("never reads a JWT query parameter", function()
        local ngx = ngx_factory.new({
            var = { arg_jwt = "must-not-be-used" }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("propagates a valid JTI cookie", function()
        local ngx = ngx_factory.new({
            cache = { ["username:jti"] = "alice", ["exp:alice"] = "500" },
            var = { http_cookie = "JTI=jti" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
    end)
end)

return runner
