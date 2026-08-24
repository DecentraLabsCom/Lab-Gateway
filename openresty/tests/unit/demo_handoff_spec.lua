local runner        = require "tests.helpers.runner"
local ngx_factory   = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local cjson         = require "cjson.safe"
local handoff       = require "modules.demo_handoff"

local function available_response(value)
    return HttpClientStub.new({
        { status = 200, body = cjson.encode({ eligible = value, labId = "42", start = "101", ["end"] = "700" }) }
    })
end

local function build_ngx(opts)
    opts = opts or {}
    local ngx = ngx_factory.new({
        method = opts.method or "GET",
        now = 100,
        config = {
            demo_user = "demo",
            demo_lab_id = "42",
            demo_connection_id = "7",
            marketplace_url = "https://marketplace.example",
            demo_session_ttl_seconds = 600,
            demo_rate_limit_per_minute = 10,
        },
        var = {
            remote_addr = "198.51.100.10",
            arg_labId = opts.lab_id_arg ~= nil and opts.lab_id_arg or "42",
        },
        cache = opts.cache,
        demo_sessions = opts.demo_sessions,
        demo_issue_rate = opts.demo_issue_rate,
    })
    local readiness_status = opts.readiness_status or 200
    ngx.location.capture = function(path)
        if path == "/gateway/health" then
            return {
                status = opts.gateway_health_status or 200,
                body = cjson.encode({ status = opts.gateway_health_status == 503 and "PARTIAL" or "UP" })
            }
        end
        if path ~= "/__health_ops" then return nil end
        return {
            status = readiness_status,
            body = cjson.encode({
                status = readiness_status == 200 and "ok" or "degraded",
                demo = {
                    status = opts.demo_readiness_status or "ready",
                    labId = "42",
                    connectionId = 7,
                    checks = {
                        connection = true,
                        principal = true,
                        permission = true,
                        physical_host = true
                    }
                }
            })
        }
    end
    return ngx
end

local function run_handoff(ngx, deps)
    deps = deps or {}
    deps.demo_station = deps.demo_station or {
        start = function() return true end,
        finish = function() return true end,
    }
    handoff.run(ngx, deps)
end

runner.describe("Demo browser handoff", function()
    runner.it("issues an isolated DEMO_JTI and redirects to Guacamole", function()
        local ngx = build_ngx()
        run_handoff(ngx, {
            http_factory = function() return available_response(true) end,
            random_bytes = function() return string.rep("a", 32) end,
        })

        runner.assert.equals(303, ngx._redirect.status)
        runner.assert.equals("/guacamole/", ngx._redirect.uri)
        runner.assert.truthy(ngx.header["Set-Cookie"]:match("^DEMO_JTI=" .. string.rep("61", 32)))
        runner.assert.truthy(ngx.header["Set-Cookie"]:match("Max%-Age=600"))
        runner.assert.equals("demo", ngx.shared.cache:get("demo_session:" .. string.rep("61", 32)))
        runner.assert.equals(600, ngx.shared.cache._ttls["demo_session:" .. string.rep("61", 32)])
        runner.assert.equals(1, ngx.shared.demo_sessions:get("occupied"))
        runner.assert.equals("pending", ngx.shared.demo_sessions:get("session:" .. string.rep("61", 32)))
    end)

    runner.it("fails closed when the demo lab is reserved", function()
        local ngx = build_ngx()
        run_handoff(ngx, {
            http_factory = function() return available_response(false) end,
            random_bytes = function() return string.rep("b", 32) end,
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("occupied"))
        runner.assert.equals(nil, ngx._redirect)
    end)

    runner.it("fails closed when the local demo readiness is not ready", function()
        local ngx = build_ngx({ readiness_status = 503 })
        run_handoff(ngx, {
            http_factory = function() return available_response(true) end,
            random_bytes = function() return string.rep("r", 32) end,
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("occupied"))
    end)

    runner.it("fails closed when the gateway aggregate is not UP", function()
        local ngx = build_ngx({ gateway_health_status = 503 })
        run_handoff(ngx, {
            http_factory = function() return available_response(true) end,
            random_bytes = function() return string.rep("g", 32) end,
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("occupied"))
    end)

    runner.it("releases the demo slot when Station preparation fails", function()
        local ngx = build_ngx()
        local finished = false
        run_handoff(ngx, {
            http_factory = function() return available_response(true) end,
            random_bytes = function() return string.rep("p", 32) end,
            demo_station = {
                start = function() return false, "prepare failed" end,
                finish = function() finished = true return true end,
            },
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(0, ngx.shared.demo_sessions:get("occupied"))
        runner.assert.equals(true, finished)
    end)

    runner.it("does not issue a session when the handoff method is not GET", function()
        local ngx = build_ngx({ method = "POST" })
        run_handoff(ngx, { random_bytes = function() return string.rep("c", 32) end })

        runner.assert.equals(405, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("occupied"))
    end)

    runner.it("rejects a handoff for a different lab", function()
        local ngx = build_ngx({ lab_id_arg = "43" })
        run_handoff(ngx, { random_bytes = function() return string.rep("d", 32) end })

        runner.assert.equals(404, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("occupied"))
        runner.assert.equals(nil, ngx._redirect)
    end)

    runner.it("rejects a handoff without a valid lab identifier", function()
        local ngx = build_ngx({ lab_id_arg = "not-a-lab" })
        run_handoff(ngx, { random_bytes = function() return string.rep("e", 32) end })

        runner.assert.equals(400, ngx.status)
        runner.assert.equals(nil, ngx.shared.demo_sessions:get("active"))
    end)
end)

return runner
