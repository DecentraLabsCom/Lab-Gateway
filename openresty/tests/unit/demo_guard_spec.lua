local runner        = require "tests.helpers.runner"
local ngx_factory   = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local cjson         = require "cjson.safe"
local DemoGuard     = require "modules.demo_guard"

-- ─── helpers ──────────────────────────────────────────────────────────────────

local function build_ngx(opts)
    opts = opts or {}
    -- Allow callers to pass "" explicitly; nil falls back to the defaults.
    local lab_id         = opts.lab_id         ~= nil and opts.lab_id         or "42"
    local marketplace    = opts.marketplace_url ~= nil and opts.marketplace_url or "https://mp.example.com"
    local config = {
        demo_user       = opts.demo_user or "demo",
        demo_lab_id     = lab_id,
        marketplace_url = marketplace,
        demo_session_ttl_seconds = opts.demo_session_ttl_seconds or 600,
        demo_pending_lease_seconds = opts.demo_pending_lease_seconds or 45,
    }
    local ngx = ngx_factory.new({
        config             = config,
        demo_sessions      = opts.demo_sessions or {},
        demo_sessions_dict = opts.demo_sessions_dict,
        now                = opts.now,
        ctx                = opts.ctx or {
            demo_authenticated = opts.demo_authenticated ~= false,
            jwt_jti = opts.jti or "demo-jti",
            demo_jti = opts.jti or "demo-jti",
            jwt_exp = opts.exp or 1000,
        },
    })
    if opts.auth ~= nil then
        ngx.req.headers["Authorization"] = opts.auth
    end
    return ngx
end

local function make_http_stub(is_available, start_time, end_time)
    return HttpClientStub.new({
        { status = 200, body = cjson.encode({
            eligible = is_available,
            labId = "42",
            start = start_time or "1",
            ["end"] = end_time or "600",
        }) }
    })
end

-- Run the guard with an injectable HTTP stub (defaults to fail-open on no response).
local function run(ngx, http_stub)
    local deps = {
        http_factory = http_stub
            and function() return http_stub end
            or  function() return HttpClientStub.new({}) end
    }
    if ngx.ctx.demo_authenticated and not ngx.shared.demo_sessions:get("session:" .. ngx.ctx.demo_jti) then
        local ttl, err = DemoGuard.start(ngx, ngx.ctx.demo_jti, ngx.ctx.jwt_exp, deps)
        if not ttl then
            ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
            ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
            return
        end
    end
    DemoGuard.run(ngx, deps)
end

-- ─── tests ────────────────────────────────────────────────────────────────────

runner.describe("Demo guard", function()

    runner.it("passes through immediately for a regular (non-demo) user", function()
        local ngx = build_ngx({ auth = "alice", demo_authenticated = false })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("passes through when Authorization header is absent", function()
        local ngx = build_ngx({ demo_authenticated = false })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("allows demo user when lab is available and no concurrent session exists", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, make_http_stub(true))
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(1, ngx.shared.demo_sessions:get("occupied"))
        runner.assert.equals("pending", ngx.shared.demo_sessions:get("session:" .. ngx.ctx.demo_jti))
    end)

    runner.it("checks the complete demo lifetime and starts just after the chain clock", function()
        local ngx = build_ngx({ auth = "demo", now = 200, exp = 800 })
        local http_stub = make_http_stub(true, "201", "800")
        run(ngx, http_stub)

        runner.assert.equals(
            "https://mp.example.com/api/demo/eligibility?labId=42&start=201&end=800",
            http_stub.calls[1].url
        )
    end)

    runner.it("rejects demo user with 503 when lab has an active reservation", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, make_http_stub(false))   -- eligible = false → lab is busy
        runner.assert.equals(503, ngx.status)
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects demo user when HTTP availability check returns a network error", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({}))  -- empty → "no response" error
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects demo user when availability endpoint returns a non-200 status", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({ { status = 503, body = "" } }))
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects demo user when availability response body is invalid JSON", function()
        local ngx = build_ngx({ auth = "demo" })
        run(ngx, HttpClientStub.new({ { status = 200, body = "not-json" } }))
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects when marketplace_url is not configured", function()
        local ngx = build_ngx({ auth = "demo", marketplace_url = "" })
        run(ngx, HttpClientStub.new({}))
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects when demo_lab_id is not configured", function()
        local ngx = build_ngx({ auth = "demo", lab_id = "" })
        run(ngx, HttpClientStub.new({}))
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("rejects demo user with 503 when a concurrent demo session is already active", function()
        local ngx = build_ngx({ auth = "demo", demo_sessions = { occupied = 1, ["session:other-jti"] = "active" } })
        run(ngx, make_http_stub(true))
        runner.assert.equals(503, ngx.status)
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("is case-insensitive when comparing the demo username", function()
        local ngx = build_ngx({ auth = "DEMO", demo_user = "demo" })
        run(ngx, make_http_stub(true))
        -- Falls into the demo path; lab free and no session → allowed
        runner.assert.equals(nil, ngx._exit_code)
        runner.assert.equals(1, ngx.shared.demo_sessions:get("occupied"))
    end)

    runner.it("rejects demo user when the session counter cannot be updated", function()
        local bad_sessions = ngx_factory.new_shared_dict()
        function bad_sessions:incr(_key, _amount, _default, _ttl)
            return nil, "simulated incr error"
        end
        local ngx = build_ngx({ auth = "demo", demo_sessions_dict = bad_sessions })
        run(ngx, make_http_stub(true))
        runner.assert.equals(503, ngx._exit_code)
    end)

    runner.it("registers a demo JTI once even when assets trigger repeated requests", function()
        local sessions = ngx_factory.new_shared_dict()
        local first = build_ngx({ auth = "demo", demo_sessions_dict = sessions, jti = "same-jti" })
        run(first, make_http_stub(true))
        local second = build_ngx({ auth = "demo", demo_sessions_dict = sessions, jti = "same-jti" })
        run(second, HttpClientStub.new({}))
        runner.assert.equals(nil, second._exit_code)
        runner.assert.equals(1, sessions:get("occupied"))
        runner.assert.equals("pending", sessions:get("session:same-jti"))
    end)

    runner.it("keeps a pending handoff on a short lease and promotes it only after Guacamole", function()
        local sessions = ngx_factory.new_shared_dict()
        local ngx = build_ngx({
            auth = "demo",
            demo_sessions_dict = sessions,
            now = 100,
            exp = 700,
        })
        run(ngx, make_http_stub(true, "101", "700"))

        runner.assert.equals("pending", sessions:get("session:demo-jti"))
        runner.assert.equals(1, sessions:get("occupied"))
        runner.assert.equals(145, ngx.shared.cache:get("demo_pending_exp:demo-jti"))

        runner.assert.equals(true, DemoGuard.activate(ngx, "demo-jti", 700))
        runner.assert.equals("active", sessions:get("session:demo-jti"))
        runner.assert.equals(nil, ngx.shared.cache:get("demo_pending_exp:demo-jti"))
        runner.assert.equals(600, sessions._ttls.occupied)
    end)

    runner.it("releases a registered demo JTI without making the active count negative", function()
        local sessions = ngx_factory.new_shared_dict({ occupied = 1, ["session:demo-jti"] = "active" })
        local ngx = build_ngx({ auth = "demo", demo_sessions_dict = sessions })
        runner.assert.truthy(DemoGuard.release(ngx, "demo-jti"))
        runner.assert.equals(nil, sessions:get("session:demo-jti"))
        runner.assert.equals(0, sessions:get("occupied"))
        runner.assert.equals(false, DemoGuard.release(ngx, "demo-jti"))
    end)

end)

return runner
