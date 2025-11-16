local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.access_handler"

runner.describe("Access handler", function()
    runner.it("ignores requests without cookies", function()
        local ngx = ngx_factory.new()
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"], "Authorization header should not be set")
    end)

    runner.it("rejects unknown JTI", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "foo=bar; JTI=abc123" }
        })

        handler.run(ngx)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("rejects when expiration is missing", function()
        local cache = { ["username:abc"] = "alice" }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=abc" }
        })

        handler.run(ngx)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("rejects expired sessions", function()
        local cache = {
            ["username:abc"] = "alice",
            ["exp:alice"] = tostring(100)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=abc" },
            now = 200
        })

        handler.run(ngx)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    runner.it("sets Authorization header for valid cookies", function()
        local cache = {
            ["username:token123"] = "alice",
            ["exp:alice"] = tostring(500)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "foo=bar; JTI=token123" },
            now = 100
        })

        handler.run(ngx)
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)
end)

return runner
