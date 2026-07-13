local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.header_filter_handler"

runner.describe("Header filter clean redirects", function()
    runner.it("enqueues JWT-backed Guacamole session observation when the websocket upgrade succeeds", function()
        local reported = false
        local ngx = ngx_factory.new({
            status = 101,
            var = { uri = "/guacamole/websocket-tunnel", args = "token=guac-token" },
            header = {}
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function(context)
                    runner.assert.equals(ngx, context)
                    reported = true
                    return true
                end
            }
        })

        runner.assert.truthy(reported)
    end)

    runner.it("refuses the websocket when its first observation is not durable", function()
        local ngx = ngx_factory.new({
            status = 101,
            var = { uri = "/guacamole/websocket-tunnel", args = "token=guac-token" },
            header = {
                Upgrade = "websocket",
                Connection = "upgrade",
                ["Sec-WebSocket-Accept"] = "accept-value"
            }
        })

        handler.run(ngx, {
            access_audit_reporter = {
                report_guacamole_session_observed = function()
                    return false, "outbox unavailable"
                end
            }
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals(nil, ngx.header.Upgrade)
        runner.assert.equals(nil, ngx.header["Sec-WebSocket-Accept"])
    end)

    runner.it("rewrites relative redirects to the gateway origin", function()
        local ngx = ngx_factory.new({
            config = { https_port = "8443", server_name = "gateway.local" },
            status = 303,
            header = { Location = "/guacamole/" }
        })
        handler.run(ngx)
        runner.assert.equals("https://gateway.local:8443/guacamole/", ngx.header.Location)
    end)

    runner.it("does not process JWT query parameters", function()
        local ngx = ngx_factory.new({
            status = 200,
            var = { arg_jwt = "must-not-be-used" },
            header = {}
        })
        handler.run(ngx)
        runner.assert.equals(nil, ngx.header["Set-Cookie"])
    end)
end)

return runner
