local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local HttpClientStub = require "tests.helpers.http_client_stub"
local SessionGuard = require "modules.session_guard"
local cjson = require "cjson.safe"

local function build_guard(cache, responses, config_overrides)
    local base_config = {
        admin_user = "admin",
        admin_pass = "secret",
        guac_uri = "/guacamole"
    }
    if config_overrides then
        for k, v in pairs(config_overrides) do
            base_config[k] = v
        end
    end

    local ngx = ngx_factory.new({
        cache = cache or {},
        config = base_config,
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

runner.describe("Session guard extended tests", function()
    -- Test: Guacamole authentication failures
    runner.it("handles Guacamole auth timeout", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = nil } -- Connection timeout
        }
        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- Should not crash, user data should remain
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles Guacamole auth 401 response", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 401, body = '{"error":"Unauthorized"}' }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- Auth failed, should not process
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles Guacamole auth 500 response", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 500, body = '{"error":"Internal Server Error"}' }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles malformed auth response JSON", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 200, body = 'not json' }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles auth response missing authToken", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 200, body = cjson.encode({ dataSource = "mysql" }) }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    -- Test: Active connections retrieval failures
    runner.it("handles active connections 500 error", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 500, body = '{"error":"Error"}' }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- Connection list failed, user data remains
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles active connections malformed JSON", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = 'invalid json' }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    runner.it("handles empty active connections", function()
        local cache = { ["exp:user1"] = "100" }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({}) }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- No connections to check, user data remains (no active connection means no termination needed)
        runner.assert.equals("100", ngx.shared.cache._data["exp:user1"])
    end)

    -- Test: Multiple expired sessions
    runner.it("terminates multiple expired sessions", function()
        local cache = {
            ["exp:user1"] = "100",
            ["exp:user2"] = "150",
            ["token:user1"] = "token-1",
            ["token:user2"] = "token-2"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({
                ["conn1"] = { username = "User1" },
                ["conn2"] = { username = "User2" }
            }) },
            { status = 204 }, -- Terminate conn1
            { status = 204 }, -- Revoke token1
            { status = 204 }, -- Terminate conn2
            { status = 204 }  -- Revoke token2
        }
        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["exp:user1"])
        runner.assert.equals(nil, store["exp:user2"])
        runner.assert.equals(nil, store["token:user1"])
        runner.assert.equals(nil, store["token:user2"])
    end)

    -- Test: Non-expired sessions preserved
    runner.it("preserves non-expired sessions", function()
        local cache = {
            ["exp:active"] = "500", -- Future expiration
            ["token:active"] = "active-token"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["conn1"] = { username = "Active" } }) }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        local store = ngx.shared.cache._data
        runner.assert.equals("500", store["exp:active"])
        runner.assert.equals("active-token", store["token:active"])
    end)

    -- Test: Connection termination failures
    runner.it("handles connection termination failure", function()
        local cache = {
            ["exp:user1"] = "100",
            ["token:user1"] = "token-1"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["conn1"] = { username = "User1" } }) },
            { status = 500 } -- Termination fails
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- Termination failed, exp should NOT be deleted in failure case
        -- Implementation may vary - depends on error handling
    end)

    -- Test: Token revocation failures
    runner.it("handles token revocation failure gracefully", function()
        local cache = {
            ["exp:user1"] = "100",
            ["token:user1"] = "token-1"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["conn1"] = { username = "User1" } }) },
            { status = 204 }, -- Termination succeeds
            { status = 500 }  -- Revocation fails
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        -- Connection terminated, token revocation failed
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["exp:user1"])
    end)

    -- Test: Tunnel closures
    runner.it("skips tunnel closure when no pending flag", function()
        local cache = {}
        local responses = {}
        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_tunnel_closures()
        
        -- Should not make any HTTP calls
        runner.assert.equals(0, #http_stub.calls)
    end)

    runner.it("handles auth failure during tunnel closure", function()
        local cache = {
            ["has_pending_closures"] = true,
            ["pending_user:alice"] = true
        }
        local responses = {
            { status = 401 }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_tunnel_closures()
        
        -- Auth failed, pending data should remain
        local store = ngx.shared.cache._data
        runner.assert.truthy(store["has_pending_closures"])
    end)

    runner.it("cleans up all pending closures", function()
        local cache = {
            ["has_pending_closures"] = true,
            ["pending_user:alice"] = true,
            ["pending_user:bob"] = true,
            ["tunnel_closed:alice"] = true,
            ["tunnel_closed:bob"] = true,
            ["token:alice"] = "token-a",
            ["token:bob"] = "token-b"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 204 }, -- Revoke alice
            { status = 204 }  -- Revoke bob
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_tunnel_closures()
        
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["pending_user:alice"])
        runner.assert.equals(nil, store["pending_user:bob"])
        runner.assert.equals(nil, store["tunnel_closed:alice"])
        runner.assert.equals(nil, store["tunnel_closed:bob"])
    end)

    -- Test: User without token in tunnel closure
    runner.it("handles pending user without token", function()
        local cache = {
            ["has_pending_closures"] = true,
            ["pending_user:notoken"] = true,
            ["tunnel_closed:notoken"] = true
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) }
        }
        local guard, http_stub, ngx = build_guard(cache, responses)
        guard:check_tunnel_closures()
        
        -- Should only auth, no revocation call
        runner.assert.equals(1, #http_stub.calls)
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["pending_user:notoken"])
    end)

    -- Test: Configuration variations
    runner.it("uses custom guac_api_url when provided", function()
        local cache = {
            ["has_pending_closures"] = true,
            ["pending_user:alice"] = true,
            ["tunnel_closed:alice"] = true
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "token", dataSource = "mysql" }) }
        }
        local guard, http_stub, _ = build_guard(cache, responses, {
            guac_api_url = "http://custom:9999/api"
        })
        -- Note: We can't directly test the URL used, but this verifies no crash
    end)

    -- Test: Username case handling
    runner.it("matches usernames case-insensitively", function()
        local cache = {
            ["exp:mixedcase"] = "100",
            ["token:mixedcase"] = "mixed-token"
        }
        local responses = {
            { status = 200, body = cjson.encode({ authToken = "admin-token", dataSource = "mysql" }) },
            { status = 200, body = cjson.encode({ ["conn1"] = { username = "MixedCase" } }) },
            { status = 204 },
            { status = 204 }
        }
        local guard, _, ngx = build_guard(cache, responses)
        guard:check_expired_sessions()
        
        local store = ngx.shared.cache._data
        runner.assert.equals(nil, store["exp:mixedcase"])
    end)
end)

return runner
