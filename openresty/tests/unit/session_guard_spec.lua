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
            guac_uri = "/guacamole"
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
            ["exp:user1"] = "100",
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
        runner.assert.equals(nil, store["exp:user1"])
        runner.assert.equals(nil, store["token:user1"])
        runner.assert.equals(nil, store["guac_token:token-1"])
        runner.assert.equals(4, #http_stub.calls)
    end)

    runner.it("skips revocation when token is missing", function()
        local cache = {
            ["exp:user1"] = "100"
        }

        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["1"] = { username = "User1" } }) },
            { status = 204 }
        }

        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["exp:user1"])
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
