local runner        = require "tests.helpers.runner"
local ngx_factory   = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local cjson         = require "cjson.safe"
local handoff       = require "modules.demo_handoff"

local function available_response(value)
    return HttpClientStub.new({
        { status = 200, body = cjson.encode({ isAvailable = value }) }
    })
end

local function build_ngx(opts)
    opts = opts or {}
    return ngx_factory.new({
        method = opts.method or "GET",
        now = 100,
        var = { remote_addr = "198.51.100.10" },
        config = {
            demo_user = "demo",
            demo_lab_id = "42",
            demo_connection_id = "7",
            marketplace_url = "https://marketplace.example",
            demo_session_ttl_seconds = 600,
            demo_rate_limit_per_minute = 10,
        },
        cache = opts.cache,
        demo_sessions = opts.demo_sessions,
        demo_issue_rate = opts.demo_issue_rate,
    })
end

runner.describe("Demo browser handoff", function()
    runner.it("issues an isolated DEMO_JTI and redirects to Guacamole", function()
        local ngx = build_ngx()
        handoff.run(ngx, {
            http_factory = function() return available_response(true) end,
            random_bytes = function() return string.rep("a", 32) end,
        })

        runner.assert.equals(303, ngx._redirect.status)
        runner.assert.equals("/guacamole/", ngx._redirect.uri)
        runner.assert.truthy(ngx.header["Set-Cookie"]:match("^DEMO_JTI=" .. string.rep("61", 32)))
        runner.assert.equals("demo", ngx.shared.cache:get("demo_session:" .. string.rep("61", 32)))
        runner.assert.equals(1, ngx.shared.demo_sessions:get("active"))
    end)

    runner.it("fails closed when the demo lab is reserved", function()
        local ngx = build_ngx()
        handoff.run(ngx, {
            http_factory = function() return available_response(false) end,
            random_bytes = function() return string.rep("b", 32) end,
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("active"))
        runner.assert.equals(nil, ngx._redirect)
    end)

    runner.it("does not issue a session when the handoff method is not GET", function()
        local ngx = build_ngx({ method = "POST" })
        handoff.run(ngx, { random_bytes = function() return string.rep("c", 32) end })

        runner.assert.equals(405, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("active"))
    end)
end)

return runner
