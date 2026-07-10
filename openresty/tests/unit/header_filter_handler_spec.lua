local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.header_filter_handler"

runner.describe("Header filter clean redirects", function()
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
