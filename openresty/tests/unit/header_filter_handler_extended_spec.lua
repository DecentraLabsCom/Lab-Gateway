local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.header_filter_handler"

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
        jti = "abc",
        sub = "Alice",
        iss = "https://issuer.example",
        aud = "https://gateway.local:8443/guacamole",
        exp = 200
    }
    if overrides then
        for k, v in pairs(overrides) do
            payload[k] = v
        end
    end
    return payload
end

local function jwt_stub(payload, opts)
    local stub_payload = payload or build_jwt_payload()
    return {
        load_jwt = function(_, token)
            if opts and opts.invalid_format then
                return { valid = false, reason = "invalid format" }
            end
            return { valid = true, payload = stub_payload, header = { kid = "1" } }
        end,
        verify_jwt_obj = function(_, _, object)
            if opts and opts.fail_signature then
                return { verified = false }
            end
            return { verified = true, payload = object.payload }
        end
    }
end

runner.describe("Header filter handler extended tests", function()
    -- Test: Port 443 should not add port suffix
    runner.it("uses port 443 without suffix in audience", function()
        local config = default_config()
        config.https_port = "443"
        local payload = build_jwt_payload({
            aud = "https://gateway.local/guacamole"
        })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = config,
            var = { arg_jwt = "token" },
            now = 50,
            header = {},
            status = 200
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        local cache = ngx.shared.cache._data
        runner.assert.equals("alice", cache["username:abc"])
    end)

    -- Test: Redirect rewriting for Location header (301)
    runner.it("rewrites relative Location on 301 redirect", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 301,
            header = { ["Location"] = "/some/path" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("https://gateway.local:8443/some/path", ngx.header["Location"])
    end)

    -- Test: Redirect rewriting for Location header (302)
    runner.it("rewrites relative Location on 302 redirect", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 302,
            header = { ["Location"] = "/redirect/here" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("https://gateway.local:8443/redirect/here", ngx.header["Location"])
    end)

    -- Test: No rewrite needed for absolute Location with correct port
    runner.it("rewrites absolute Location to include port", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 302,
            header = { ["Location"] = "https://other.host/path" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        -- Should rewrite to use server_name and port
        runner.assert.equals("https://gateway.local:8443/path", ngx.header["Location"])
    end)

    -- Test: Missing public key
    runner.it("skips JWT verification when public key missing", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = { arg_jwt = "token" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Invalid JWT format
    runner.it("rejects invalid JWT format", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "malformed" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub(nil, { invalid_format = true }) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Missing JTI claim
    runner.it("rejects JWT without JTI claim", function()
        local payload = build_jwt_payload()
        payload.jti = nil
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Missing sub claim
    runner.it("rejects JWT without sub claim", function()
        local payload = build_jwt_payload()
        payload.sub = nil
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Invalid issuer
    runner.it("rejects JWT with wrong issuer", function()
        local payload = build_jwt_payload({ iss = "https://wrong.issuer" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Audience with trailing slash normalization
    runner.it("normalizes audience with trailing slash", function()
        local payload = build_jwt_payload({ aud = "https://gateway.local:8443/guacamole/" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 50,
            header = {},
            status = 200
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        local cache = ngx.shared.cache._data
        runner.assert.equals("alice", cache["username:abc"])
    end)

    -- Test: JTI already registered (prevents replay)
    runner.it("skips if JTI already registered", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub", ["username:existingjti"] = "bob" },
            config = default_config(),
            var = { arg_jwt = "token" },
            header = {},
            status = 200
        })

        local payload = build_jwt_payload({ jti = "existingjti" })
        handler.run(ngx, { jwt = jwt_stub(payload) })
        -- Should not set cookie for already registered JTI
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Cookie max-age calculation
    runner.it("sets correct max-age in cookie", function()
        local payload = build_jwt_payload({ exp = 500 })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 100,
            header = {},
            status = 200
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.truthy(ngx.header["Set-Cookie"]:find("Max%-Age=400"))
    end)

    -- Test: Cookie has Secure and HttpOnly flags
    runner.it("sets Secure and HttpOnly flags on cookie", function()
        local payload = build_jwt_payload()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 50,
            header = {},
            status = 200
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        local cookie = ngx.header["Set-Cookie"]
        runner.assert.truthy(cookie:find("Secure"))
        runner.assert.truthy(cookie:find("HttpOnly"))
        runner.assert.truthy(cookie:find("SameSite=Lax"))
    end)

    -- Test: Empty jwt parameter
    runner.it("skips when jwt parameter is empty", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "" },
            header = {}
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    -- Test: Username stored in lowercase
    runner.it("stores username in lowercase", function()
        local payload = build_jwt_payload({ sub = "UPPERCASE" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 50,
            header = {},
            status = 200
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        local cache = ngx.shared.cache._data
        runner.assert.equals("uppercase", cache["username:abc"])
        runner.assert.truthy(cache["exp:uppercase"])
    end)

    -- Test: Handle 303 redirect
    runner.it("handles 303 redirect", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 303,
            header = { ["Location"] = "/redirect" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("https://gateway.local:8443/redirect", ngx.header["Location"])
    end)

    -- Test: Handle 307 redirect
    runner.it("handles 307 redirect", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 307,
            header = { ["Location"] = "/temp" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("https://gateway.local:8443/temp", ngx.header["Location"])
    end)

    -- Test: Handle 308 redirect
    runner.it("handles 308 redirect", function()
        local ngx = ngx_factory.new({
            cache = {},
            config = default_config(),
            var = {},
            status = 308,
            header = { ["Location"] = "/permanent" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        runner.assert.equals("https://gateway.local:8443/permanent", ngx.header["Location"])
    end)
end)

return runner
