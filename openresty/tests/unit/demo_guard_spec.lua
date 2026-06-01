local runner        = require "tests.helpers.runner"
local ngx_factory   = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local cjson         = require "cjson.safe"
local DemoGuard     = require "modules.demo_guard"

-- ─── helpers ──────────────────────────────────────────────────────────────────

local function build_ngx(opts)
    opts = opts or {}
    -- Allow callers to pass "" explicitly; nil falls back to the defaults.
    local lab_id         = opts.lab_id         ~= nil and opts.lab_id         or "lab42"
    local marketplace    = opts.marketplace_url ~= nil and opts.marketplace_url or "https://mp.example.com"
    local config = {
        demo_user       = opts.demo_user or "demo",
        demo_lab_id     = lab_id,
        marketplace_url = marketplace,
    }
    local ngx = ngx_factory.new({
        config             = config,
        demo_sessions      = opts.demo_sessions or {},
        demo_sessions_dict = opts.demo_sessions_dict,
    })
    if opts.auth ~= nil then
        ngx.req.headers["Authorization"] = opts.auth
    end
    return ngx
end

local function make_http_stub(is_available)
    return HttpClientStub.new({
        { status = 200, body = cjson.encode({ isAvailable = is_available }) }
    })
end

-- Run the guard with an injectable HTTP stub (defaults to fail-open on no response).
local function run(ngx, http_stub)
    local deps = {
        http_factory = http_stub
            and function() return http_stub end
            or  function() return HttpClientStub.new({}) end
    }
    DemoGuard.run(ngx, deps)
end

-- ─── tests ────────────────────────────────────────────────────────────────────

runner.describe("Demo guard", function()

    runner.it("passes through immediately for a regular (non-demo) user", function()
        local ngx = build_ngx({ auth = "alice" })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("passes through when Authorization header is absent", function()
        local ngx = build_ngx({})
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("allows demo user when lab is available and no concurrent session exists", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(1, ngx.shared.demo_sessions:get("count"))
    end)

    runner.it("rejects demo user with 503 when lab has an active reservation", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, make_http_stub(false))   -- isAvailable = false → lab is busy
        runner.assert.equals(503, ngx.status)
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("allows demo user when HTTP availability check returns a network error (fail-open)", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({}))  -- empty → "no response" error
        runner.assert.equals(nil, ngx._exit_code)
    end)

    runner.it("allows demo user when availability endpoint returns a non-200 status (fail-open)", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({ { status = 503, body = "" } }))
        runner.assert.equals(nil, ngx._exit_code)
    end)

    runner.it("allows demo user when availability response body is invalid JSON (fail-open)", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({ { status = 200, body = "not-json" } }))
        runner.assert.equals(nil, ngx._exit_code)
    end)

    runner.it("skips busy check and allows when marketplace_url is not configured (fail-open)", function()
        local ngx = build_ngx({ auth = "demo", marketplace_url = "" })
        run(ngx, HttpClientStub.new({}))
        runner.assert.equals(nil, ngx._exit_code)
    end)

    runner.it("skips busy check and allows when demo_lab_id is not configured", function()
        local ngx = build_ngx({ auth = "demo", lab_id = "" })
        run(ngx, HttpClientStub.new({}))
        runner.assert.equals(nil, ngx._exit_code)
    end)

    runner.it("rejects demo user with 503 when a concurrent demo session is already active", function()
        local ngx = build_ngx({ auth = "demo", demo_sessions = { count = 1 } })
        run(ngx, make_http_stub(true))
        runner.assert.equals(503, ngx.status)
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("is case-insensitive when comparing the demo username", function()
        local ngx = build_ngx({ auth = "DEMO", demo_user = "demo" })
        run(ngx, make_http_stub(true))
        -- Falls into the demo path; lab free and no session → allowed
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(1, ngx.shared.demo_sessions:get("count"))
    end)

    runner.it("allows demo user and continues (fail-open) when session counter incr errors", function()
        local bad_sessions = ngx_factory.new_shared_dict()
        function bad_sessions:incr(_key, _amount, _default, _ttl)
            return nil, "simulated incr error"
        end
        local ngx = build_ngx({ auth = "demo", demo_sessions_dict = bad_sessions })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
    end)

end)

return runner
