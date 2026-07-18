local runner = require "tests.helpers.runner"
local hex = require "modules.hex"

runner.describe("Hex encoder", function()
    runner.it("encodes arbitrary bytes without relying on nginx symbols", function()
        runner.assert.equals("00ff410a", hex.encode(string.char(0, 255, 65, 10)))
    end)
end)
