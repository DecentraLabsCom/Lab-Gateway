local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.guacamole_token_handler"
local cjson = require "cjson.safe"

local function response()
    return {
        status = 200,
        body = '{"authToken":"guac-token","username":"Dlabs-Res-User","dataSource":"mysql"}',
        header = { ["Content-Type"] = "application/json" },
    }
end

local function jwt_ngx(opts)
    opts = opts or {}
    return ngx_factory.new({
        cache_dict = opts.cache_dict,
        config = { server_name = "lite.lab.example" },
        ctx = opts.ctx or {
            jwt_authenticated = true,
            jwt_exp = 500,
            jwt_jti = "jwt-jti",
            jwt_reservation_key = "0xabc",
        },
        now = 100,
    })
end

runner.describe("Guacamole token content-phase handler", function()
    runner.it("registers JWT token revocation before exposing the token", function()
        local ngx = jwt_ngx()
        local registered

        local secured = handler.handle_response(ngx, response(), {
            cjson = cjson,
            revocation_reporter = {
                register = function(_, payload)
                    registered = payload
                    return true
                end,
            },
        })

        runner.assert.equals(200, secured.status)
        runner.assert.equals("guac-token", cjson.decode(secured.body).authToken)
        runner.assert.equals("guac-token", ngx.shared.cache:get("token:dlabs-res-user"))
        runner.assert.equals("jwt-jti", ngx.shared.cache:get("guac_jti:guac-token"))
        runner.assert.equals("0xabc", registered.reservationKey)
        runner.assert.equals(1600, ngx.shared.cache._ttls["guac_jti:guac-token"])
    end)

    runner.it("fails closed and removes mappings when durable registration fails", function()
        local ngx = jwt_ngx()

        local secured = handler.handle_response(ngx, response(), {
            cjson = cjson,
            revocation_reporter = {
                register = function()
                    return false, "outbox unavailable"
                end,
            },
        })

        runner.assert.equals(503, secured.status)
        runner.assert.equals("SECURITY_ERROR", cjson.decode(secured.body).type)
        runner.assert.equals(nil, ngx.shared.cache:get("token:dlabs-res-user"))
        runner.assert.equals(nil, ngx.shared.cache:get("guac_token:guac-token"))
    end)

    runner.it("fails closed when the reporter raises an error", function()
        local secured = handler.handle_response(jwt_ngx(), response(), {
            cjson = cjson,
            revocation_reporter = {
                register = function()
                    error("API disabled in the context of body_filter_by_lua*")
                end,
            },
        })

        runner.assert.equals(503, secured.status)
        runner.assert.equals("SECURITY_ERROR", cjson.decode(secured.body).type)
    end)

    runner.it("fails closed when the JWT context is incomplete", function()
        local secured = handler.handle_response(jwt_ngx({
            ctx = {
                jwt_authenticated = true,
                jwt_exp = 500,
                jwt_jti = "jwt-jti",
            },
        }), response(), { cjson = cjson })

        runner.assert.equals(503, secured.status)
        runner.assert.equals("SECURITY_ERROR", cjson.decode(secured.body).type)
    end)

    runner.it("fails closed when any security mapping cannot be stored", function()
        local dict = ngx_factory.new_shared_dict()
        local original_set = dict.set
        function dict:set(key, value, ttl)
            if key == "guac_jti:guac-token" then
                return nil, "no memory"
            end
            return original_set(key, value, ttl)
        end

        local secured = handler.handle_response(jwt_ngx({ cache_dict = dict }), response(), {
            cjson = cjson,
        })

        runner.assert.equals(503, secured.status)
        runner.assert.equals(nil, dict:get("token:dlabs-res-user"))
        runner.assert.equals(nil, dict:get("guac_jwt_exp:guac-token"))
    end)

    runner.it("preserves manual Guacamole login behavior without revocation registration", function()
        local ngx = ngx_factory.new()
        local secured = handler.handle_response(ngx, response(), {
            cjson = cjson,
            revocation_reporter = {
                register = function()
                    error("manual logins must not use the reservation queue")
                end,
            },
        })

        runner.assert.equals(200, secured.status)
        runner.assert.equals("guac-token", ngx.shared.cache:get("token:dlabs-res-user"))
    end)

    runner.it("passes through non-token and non-JSON upstream responses", function()
        local ngx = ngx_factory.new()
        local html = {
            status = 502,
            body = "upstream unavailable",
            header = { ["Content-Type"] = "text/plain" },
        }
        local ordinary_json = {
            status = 200,
            body = '{"message":"login required"}',
            header = { ["Content-Type"] = "application/json; charset=utf-8" },
        }

        runner.assert.equals(html, handler.handle_response(ngx, html, { cjson = cjson }))
        runner.assert.equals(ordinary_json, handler.handle_response(ngx, ordinary_json, { cjson = cjson }))
    end)
end)

return runner
