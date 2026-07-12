local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.body_filter_handler"
local cjson = require "cjson.safe"

local function jwt_deps()
    return {
        cjson = cjson,
        revocation_reporter = {
            persist = function() return true, "/spool/revocation.json" end,
            deliver = function() return true end,
            remove_persisted = function() return true end,
        }
    }
end

local function new_ngx(opts)
    opts = opts or {}
    local ngx = ngx_factory.new({
        header = opts.header or { ["Content-Type"] = "application/json" },
        cache = opts.cache or {},
        ctx = {}
    })
    return ngx
end

runner.describe("Body filter handler", function()
    runner.it("skips non JSON responses", function()
        local ngx = new_ngx({ header = { ["Content-Type"] = "text/html" } })
        handler.run(ngx, "{}", true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("skips invalid body format", function()
        local ngx = new_ngx()
        handler.run(ngx, "plain text", true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("stores token mappings when payload valid", function()
        local ngx = new_ngx()
        local payload = '{"authToken":"abc","username":"User"}'
        handler.run(ngx, payload, true, { cjson = cjson })
        local cache = ngx.shared.cache._data
        runner.assert.equals("abc", cache["token:user"])
        runner.assert.equals("user", cache["guac_token:abc"])
        runner.assert.equals(nil, cache["guac_jwt_exp:abc"])
        runner.assert.equals(nil, cache["guac_manual_last_seen:abc"])
    end)

    runner.it("marks JWT-backed Guacamole tokens with expiration and last-seen", function()
        local ngx = ngx_factory.new({
            header = { ["Content-Type"] = "application/json" },
            cache = {},
            ctx = {
                jwt_authenticated = true,
                jwt_jti = "jwt-jti",
                jwt_reservation_key = "0xabc",
                jwt_exp = 500
            },
            now = 100
        })

        handler.run(ngx, '{"authToken":"jwt-token","username":"JwtUser"}', true, jwt_deps())

        local cache = ngx.shared.cache._data
        runner.assert.equals("jwt-token", cache["token:jwtuser"])
        runner.assert.equals("jwtuser", cache["guac_token:jwt-token"])
        runner.assert.equals(500, cache["guac_jwt_exp:jwt-token"])
        runner.assert.equals(100, cache["guac_jwt_last_seen:jwt-token"])
        runner.assert.equals("jwt-jti", cache["guac_jti:jwt-token"])
        runner.assert.equals("0xabc", cache["guac_reservation:jwt-token"])
        runner.assert.equals(nil, cache["guac_manual_last_seen:jwt-token"])
    end)

    runner.it("retains every JWT-derived mapping beyond Guacamole's token lifetime", function()
        local ngx = ngx_factory.new({
            header = { ["Content-Type"] = "application/json" },
            cache = {},
            ctx = { jwt_authenticated = true, jwt_jti = "jwt-jti", jwt_exp = 14500 },
            now = 100
        })

        handler.run(ngx, '{"authToken":"long-token","username":"LongUser"}', true, jwt_deps())

        local ttl = ngx.shared.cache._ttls["token:longuser"]
        runner.assert.equals(15600, ttl)
        runner.assert.equals(ttl, ngx.shared.cache._ttls["guac_token:long-token"])
        runner.assert.equals(ttl, ngx.shared.cache._ttls["guac_jwt_exp:long-token"])
        runner.assert.equals(ttl, ngx.shared.cache._ttls["guac_jwt_last_seen:long-token"])
        runner.assert.equals(ttl, ngx.shared.cache._ttls["guac_jti:long-token"])
    end)

    runner.it("handles chunked responses", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"abc",', false, { cjson = cjson })
        handler.run(ngx, '"username":"Bob"}', true, { cjson = cjson })
        runner.assert.equals("abc", ngx.shared.cache._data["token:bob"])
    end)

    runner.it("skips when decode fails", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"broken"', true, {
            cjson = {
                decode = function()
                    error("boom")
                end
            }
        })
        runner.assert.equals(nil, ngx.shared.cache._data["token:any"])
    end)

    runner.it("skips when missing authToken fields", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"foo":"bar"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)
end)

return runner
