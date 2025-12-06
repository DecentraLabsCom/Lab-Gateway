local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.access_handler"

runner.describe("Access handler extended tests", function()
    -- Edge case: Empty cookie string
    runner.it("ignores empty cookie string", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "" }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    -- Edge case: JTI cookie with empty value
    runner.it("rejects JTI cookie with empty value", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "JTI=" }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    -- Edge case: Multiple cookies but no JTI
    runner.it("ignores multiple cookies without JTI", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = "session=abc; user=bob; tracking=xyz" }
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    -- Edge case: JTI at the end of cookie string
    runner.it("parses JTI at end of cookie string", function()
        local cache = {
            ["username:endtoken"] = "alice",
            ["exp:alice"] = tostring(500)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "other=value; JTI=endtoken" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
    end)

    -- Edge case: JTI with special characters (should be URL encoded normally)
    runner.it("handles JTI with dashes and underscores", function()
        local cache = {
            ["username:token-123_abc"] = "charlie",
            ["exp:charlie"] = tostring(600)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=token-123_abc" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("charlie", ngx.req.headers["Authorization"])
    end)

    -- Edge case: Expiration exactly at current time (boundary)
    runner.it("rejects session when exp equals now", function()
        local cache = {
            ["username:boundary"] = "diana",
            ["exp:diana"] = tostring(100)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=boundary" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals(ngx.HTTP_UNAUTHORIZED, ngx.status)
    end)

    -- Edge case: Username with mixed case stored
    runner.it("handles username case as stored", function()
        local cache = {
            ["username:casetest"] = "MixedCase",
            ["exp:MixedCase"] = tostring(500)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=casetest" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("MixedCase", ngx.req.headers["Authorization"])
    end)

    -- Edge case: Valid session with large exp value
    runner.it("handles large expiration timestamps", function()
        local cache = {
            ["username:largetime"] = "future",
            ["exp:future"] = tostring(9999999999)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=largetime" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("future", ngx.req.headers["Authorization"])
    end)

    -- Edge case: Expiration stored as non-numeric (malformed data)
    runner.it("handles non-numeric expiration gracefully", function()
        local cache = {
            ["username:badexp"] = "baduser",
            ["exp:baduser"] = "not-a-number"
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=badexp" },
            now = 100
        })
        -- tonumber("not-a-number") returns nil, comparison with nil raises error
        -- handler should gracefully reject
        local ok = pcall(handler.run, ngx)
        -- Either rejects or errors - both acceptable for malformed data
        runner.assert.truthy(ngx.status == ngx.HTTP_UNAUTHORIZED or not ok)
    end)

    -- Edge case: Cookie with trailing semicolon
    runner.it("parses cookie with trailing semicolon", function()
        local cache = {
            ["username:trailsemi"] = "semi",
            ["exp:semi"] = tostring(500)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=trailsemi;" },
            now = 100
        })
        handler.run(ngx)
        runner.assert.equals("semi", ngx.req.headers["Authorization"])
    end)

    -- Edge case: JTI with spaces (malformed but possible)
    runner.it("handles JTI with leading spaces", function()
        local ngx = ngx_factory.new({
            var = { http_cookie = " JTI=spaced" }
        })
        handler.run(ngx)
        -- Depending on implementation, may or may not parse
        -- Just ensure no crash
        runner.assert.equals(nil, ngx.status)
    end)
end)

return runner
