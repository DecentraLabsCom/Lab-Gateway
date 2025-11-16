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

runner.describe("Header filter handler", function()
    runner.it("stores username and cookie when JWT is valid", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" },
            now = 50,
            header = {},
            status = 200
        })

        local payload = build_jwt_payload({ sub = "Bob", jti = "token123", exp = 150 })
        handler.run(ngx, { jwt = jwt_stub(payload) })

        local cache = ngx.shared.cache._data
        runner.assert.equals("bob", cache["username:token123"])
        runner.assert.equals(150, cache["exp:bob"])
        runner.assert.truthy(ngx.header["Set-Cookie"]:find("JTI=token123"))
        runner.assert.truthy(ngx.header["Set-Cookie"]:find("Path=/guacamole"))
    end)

    runner.it("skips JWT processing if cookie already exists", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { cookie_JTI = "existing", arg_jwt = "token" }
        })

        handler.run(ngx, { jwt = jwt_stub() })
        local cache = ngx.shared.cache._data
        runner.assert.equals(nil, cache["username:abc"])
    end)

    runner.it("rejects invalid audience without setting cookie", function()
        local payload = build_jwt_payload({ aud = "https://wrong" })
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })

        handler.run(ngx, { jwt = jwt_stub(payload) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)

    runner.it("rejects invalid signature", function()
        local ngx = ngx_factory.new({
            cache = { public_key = "pub" },
            config = default_config(),
            var = { arg_jwt = "token" }
        })

        handler.run(ngx, { jwt = jwt_stub(nil, { fail_signature = true }) })
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)
end)

return runner
