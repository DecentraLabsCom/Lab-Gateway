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
    -- Note: now > exp rejects, but now == exp is still valid (not expired yet)
    runner.it("accepts session when exp equals now", function()
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
        -- now == exp means NOT expired yet (condition is now > exp)
        runner.assert.equals("diana", ngx.req.headers["Authorization"])
    end)

    -- Edge case: Expiration one second before current time
    runner.it("falls through silently when exp is before now", function()
        local cache = {
            ["username:expired"] = "eve",
            ["exp:eve"] = tostring(99)
        }
        local ngx = ngx_factory.new({
            cache = cache,
            var = { http_cookie = "JTI=expired" },
            now = 100
        })
        handler.run(ngx)
        -- Expired cookie: falls through silently so ?jwt= URL can still authenticate
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
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
        -- tonumber("not-a-number") returns nil; now <= nil is false in Lua,
        -- so the handler falls through without setting Authorization or status.
        local ok = pcall(handler.run, ngx)
        -- Either falls through silently or errors – both acceptable for malformed data.
        runner.assert.truthy(ngx.req.headers["Authorization"] == nil or not ok)
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
        -- Pattern "JTI=([^;]+)" still matches " JTI=spaced" and extracts "spaced".
        -- Since username:spaced doesn't exist, falls through silently.
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("does not apply JWT idle timeout to manual Guacamole tokens", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:manual-token"] = "admin",
                ["token:admin"] = "manual-token"
            },
            var = { arg_token = "manual-token" },
            now = 1000
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals("admin", ngx.shared.cache._data["guac_token:manual-token"])
    end)

    runner.it("refreshes non-admin manual Guacamole token last-seen while within idle timeout", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:manual-token"] = "alice",
                ["token:alice"] = "manual-token",
                ["guac_manual_last_seen:manual-token"] = 100
            },
            config = {
                admin_user = "admin",
                manual_guac_idle_timeout_seconds = 60
            },
            var = { arg_token = "manual-token" },
            now = 150
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals(150, ngx.shared.cache._data["guac_manual_last_seen:manual-token"])
    end)

    runner.it("rejects non-admin manual Guacamole tokens after idle timeout", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:manual-token"] = "alice",
                ["token:alice"] = "manual-token",
                ["guac_manual_last_seen:manual-token"] = 100
            },
            config = {
                admin_user = "admin",
                manual_guac_idle_timeout_seconds = 60
            },
            var = { arg_token = "manual-token" },
            now = 161
        })

        handler.run(ngx)

        runner.assert.equals(401, ngx.status)
        runner.assert.equals(401, ngx._exit_code)
        runner.assert.equals(100, ngx.shared.cache._data["guac_manual_last_seen:manual-token"])
    end)

    runner.it("does not apply non-admin manual idle timeout to admin Guacamole token", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:manual-token"] = "admin",
                ["token:admin"] = "manual-token",
                ["guac_manual_last_seen:manual-token"] = 100
            },
            config = {
                admin_user = "admin",
                manual_guac_idle_timeout_seconds = 60
            },
            var = { arg_token = "manual-token" },
            now = 1000
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals(100, ngx.shared.cache._data["guac_manual_last_seen:manual-token"])
    end)

    runner.it("refreshes JWT-backed Guacamole token last-seen while within idle timeout", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:jwt-token"] = "alice",
                ["token:alice"] = "jwt-token",
                ["guac_jwt_exp:jwt-token"] = 1000,
                ["guac_jwt_last_seen:jwt-token"] = 100
            },
            config = { jwt_guac_idle_timeout_seconds = 60 },
            var = { arg_token = "jwt-token" },
            now = 150
        })

        handler.run(ngx)

        runner.assert.equals(nil, ngx.status)
        runner.assert.equals(150, ngx.shared.cache._data["guac_jwt_last_seen:jwt-token"])
    end)

    runner.it("rejects JWT-backed Guacamole tokens after idle timeout", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:jwt-token"] = "alice",
                ["token:alice"] = "jwt-token",
                ["guac_jwt_exp:jwt-token"] = 1000,
                ["guac_jwt_last_seen:jwt-token"] = 100
            },
            config = { jwt_guac_idle_timeout_seconds = 60 },
            var = { arg_token = "jwt-token" },
            now = 161
        })

        handler.run(ngx)

        runner.assert.equals(401, ngx.status)
        runner.assert.equals(401, ngx._exit_code)
        runner.assert.equals("alice", ngx.shared.cache._data["guac_token:jwt-token"])
        runner.assert.equals("jwt-token", ngx.shared.cache._data["token:alice"])
        runner.assert.equals(1000, ngx.shared.cache._data["guac_jwt_exp:jwt-token"])
        runner.assert.equals(100, ngx.shared.cache._data["guac_jwt_last_seen:jwt-token"])
    end)

    runner.it("rejects JWT-backed Guacamole tokens after JWT expiration", function()
        local ngx = ngx_factory.new({
            cache = {
                ["guac_token:jwt-token"] = "alice",
                ["token:alice"] = "jwt-token",
                ["guac_jwt_exp:jwt-token"] = 200,
                ["guac_jwt_last_seen:jwt-token"] = 199
            },
            config = { jwt_guac_idle_timeout_seconds = 60 },
            var = { arg_token = "jwt-token" },
            now = 201
        })

        handler.run(ngx)

        runner.assert.equals(401, ngx.status)
        runner.assert.equals(401, ngx._exit_code)
    end)
end)

-- ── JWT-from-URL fallback (access phase) ─────────────────────────────────────
local function default_config()
    return {
        issuer = "https://issuer.example",
        https_port = "8443",
        server_name = "gateway.local",
        guac_uri = "/guacamole"
    }
end

local function build_jwt_payload(overrides)
    local payload = {
        jti = "jti-url-1",
        sub = "Bob",
        iss = "https://issuer.example",
        aud = "https://gateway.local:8443/guacamole",
        exp = 500
    }
    if overrides then
        for k, v in pairs(overrides) do payload[k] = v end
    end
    return payload
end

local function jwt_stub(payload, opts)
    local p = payload or build_jwt_payload()
    return {
        load_jwt = function(_, _token)
            if opts and opts.invalid_format then
                return { valid = false, reason = "bad format" }
            end
            return { valid = true, payload = p }
        end,
        verify_jwt_obj = function(_, _, obj)
            if opts and opts.fail_signature then
                return { verified = false }
            end
            return { verified = true, payload = obj.payload }
        end
    }
end

runner.describe("Access handler – JWT from URL fallback", function()
    runner.it("sets Authorization header when valid JWT in ?jwt= and no cookie", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("bob", ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("stores username and exp in shared dict", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub() })
        local cache = ngx.shared.cache._data
        runner.assert.equals("bob", cache["username:jti-url-1"])
        runner.assert.equals(500, cache["exp:bob"])
    end)

    runner.it("does nothing when ?jwt= is absent and no cookie", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = {}
        })
        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.status)
    end)

    runner.it("ignores ?jwt= when JTI cookie is present and valid", function()
        local ngx = ngx_factory.new({
            cache = {
                public_key = "pub",
                ["username:existing-jti"] = "alice",
                ["exp:alice"] = tostring(600)
            },
            config = default_config(),
            var = { http_cookie = "JTI=existing-jti", arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub() })
        -- Cookie path wins; sub from JWT ("bob") must NOT be used
        runner.assert.equals("alice", ngx.req.headers["Authorization"])
    end)

    runner.it("skips when public key is missing", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("skips on invalid JWT format", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "malformed" }
        })
        handler.run(ngx, { jwt = jwt_stub(nil, { invalid_format = true }) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("skips on failed JWT signature", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub(nil, { fail_signature = true }) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("rejects mismatched issuer", function()
        local payload = build_jwt_payload({ iss = "https://wrong-issuer.example" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("rejects mismatched audience", function()
        local payload = build_jwt_payload({ aud = "https://wrong-audience.example/guac" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("accepts trailing-slash audience via normalization", function()
        local payload = build_jwt_payload({ aud = "https://gateway.local:8443/guacamole/" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals("bob", ngx.req.headers["Authorization"])
    end)

    runner.it("rejects expired JWT from URL before setting Authorization", function()
        local payload = build_jwt_payload({ exp = 99 })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.shared.cache._data["username:jti-url-1"])
    end)

    runner.it("rejects not-yet-valid JWT from URL before setting Authorization", function()
        local payload = build_jwt_payload({ nbf = 101 })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
        runner.assert.equals(nil, ngx.shared.cache._data["username:jti-url-1"])
    end)

    runner.it("skips when JWT is missing jti claim", function()
        local payload = build_jwt_payload()
        payload.jti = nil
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("skips when JWT is missing sub claim", function()
        local payload = build_jwt_payload()
        payload.sub = nil
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.req.headers["Authorization"])
    end)

    runner.it("lowercases the username from sub claim", function()
        local payload = build_jwt_payload({ sub = "UPPER_USER" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100
        })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals("upper_user", ngx.req.headers["Authorization"])
    end)
end)

return runner
