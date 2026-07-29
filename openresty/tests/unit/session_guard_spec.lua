local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local SessionGuard = require "modules.session_guard"
local cjson = require "cjson.safe"

local function build_guard(cache, responses)
    local ngx = ngx_factory.new({
        cache = cache or {},
        config = {
            admin_user = "admin",
            admin_pass = "secret",
            guac_uri = "/guacamole",
            marketplace_url = "https://mp.example.com",
            demo_lab_id = "42"
        },
        now = 200
    })

    local http_stub = HttpClientStub.new(responses)
    local guard = SessionGuard.new({
        ngx = ngx,
        dict = ngx.shared.cache,
        config = ngx.shared.config,
        http_factory = function()
            return http_stub
        end,
        cjson = cjson
    })
    return guard, http_stub, ngx
end

runner.describe("Session guard", function()
    runner.it("terminates expired sessions and revokes tokens", function()
        local cache = {
            ["guac_enforcement_exp:user1"] = "100",
            ["token:user1"] = "token-1"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["123"] = { username = "User1" } }) },
            { status = 204 },
            { status = 204 }
        }

        local guard, http_stub, ngx = build_guard(cache, responses)

        guard:check_expired_sessions()

        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["guac_enforcement_exp:user1"])
        runner.assert.equals(nil, store["token:user1"])
        runner.assert.equals(nil, store["guac_token:token-1"])
        runner.assert.equals(4, #http_stub.calls)
    end)

    runner.it("revokes an expired JWT token even without an active connection", function()
        local cache = {
            ["guac_enforcement_exp:user1"] = "100",
            ["guac_jwt_exp:token-1"] = "100",
            ["guac_jwt_last_seen:token-1"] = "90",
            ["guac_jti:token-1"] = "jti-1",
            ["guac_reservation:token-1"] = "0xabc",
            ["guac_token:token-1"] = "user1",
            ["token:user1"] = "token-1"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({}) },
            { status = 204 }
        }

        local guard, http_stub, ngx = build_guard(cache, responses)

        guard:check_expired_sessions()

        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["guac_enforcement_exp:user1"])
        runner.assert.equals(nil, store["guac_jwt_exp:token-1"])
        runner.assert.equals(nil, store["guac_jti:token-1"])
        runner.assert.equals(nil, store["guac_reservation:token-1"])
        runner.assert.equals(nil, store["guac_token:token-1"])
        runner.assert.equals(nil, store["token:user1"])
        runner.assert.equals(3, #http_stub.calls)
    end)

    runner.it("skips revocation when token is missing", function()
        local cache = {
            ["guac_enforcement_exp:user1"] = "100"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["1"] = { username = "User1" } }) },
            { status = 204 }
        }

        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["guac_enforcement_exp:user1"])
    end)

    runner.it("does not infer an active-session expiry from the short-lived request key", function()
        local cache = {
            ["exp:user1"] = "100",
            ["token:user1"] = "token-1"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["123"] = { username = "User1" } }) }
        }

        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()

        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
        runner.assert.equals("token-1", ngx.shared.cache._data["token:user1"])
        runner.assert.equals(2, #http_stub.calls)
    end)

    runner.it("checks active-session expirations every ten seconds", function()
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({}) }
        }
        local guard, _, ngx = build_guard({}, responses)

        guard:start()
        runner.assert.equals(10, ngx._timer_calls.at[1].delay)
        ngx._timer_calls.at[1].callback(false)

        runner.assert.equals(10, ngx._timer_calls.every[1].interval)
        runner.assert.equals(2, ngx._timer_calls.every[2].interval)
    end)

    runner.it("revokes an active demo when a paid reservation now overlaps it", function()
        local cache = {
            ["guac_demo:token-1"] = "demo-jti",
            ["guac_jti:token-1"] = "demo-jti",
            ["guac_jwt_exp:token-1"] = "800",
            ["guac_token:token-1"] = "demo",
            ["token:demo"] = "token-1"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["123"] = { username = "demo" } }) },
            { status = 200, body = cjson.encode({ isAvailable = false }) },
            { status = 204 },
            { status = 204 }
        }

        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_demo_sessions()

        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["guac_demo:token-1"])
        runner.assert.equals(nil, store["guac_jwt_exp:token-1"])
        runner.assert.equals(nil, store["token:demo"])
        runner.assert.equals(5, #http_stub.calls)
        runner.assert.truthy(http_stub.calls[3].url:match("start=201"))
        runner.assert.truthy(http_stub.calls[3].url:match("end=800"))
    end)

    runner.it("processes tunnel closures and cleans pending flags", function()
        local cache = {
            ["has_pending_closures"] = true,
            ["pending_user:alice"] = true,
            ["tunnel_closed:alice"] = true,
            ["token:alice"] = "guac-token"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 204 }
        }

        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_tunnel_closures()
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["pending_user:alice"])
        runner.assert.equals(nil, store["tunnel_closed:alice"])
        runner.assert.equals(nil, store["token:alice"])
        runner.assert.equals(nil, store["has_pending_closures"])
        runner.assert.equals(2, #http_stub.calls)
    end)
end)

return runner
