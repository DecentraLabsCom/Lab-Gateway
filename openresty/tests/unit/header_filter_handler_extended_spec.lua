local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.header_filter_handler"

runner.describe("Header filter redirect policy", function()
    runner.it("leaves absolute redirects unchanged", function()
        local ngx = ngx_factory.new({
            config = { https_port = "443", server_name = "gateway.local" },
            status = 302,
            header = { Location = "https://gateway.local/guacamole/" }
        })
        handler.run(ngx)
        runner.assert.equals("https://gateway.local/guacamole/", ngx.header.Location)
    end)
end)

return runner
