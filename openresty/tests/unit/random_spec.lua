local runner = require "tests.helpers.runner"
local random = require "resty.random"

runner.describe("Random byte generator", function()
    runner.it("returns cryptographically random bytes of the requested length", function()
        local first = random.bytes(32, true)
        local second = random.bytes(32, true)

        runner.assert.truthy(first)
        runner.assert.truthy(second)
        runner.assert.equals(32, #first)
        runner.assert.equals(32, #second)
        if first == second then
            error("random byte sequences unexpectedly matched")
        end
    end)

    runner.it("rejects invalid byte lengths", function()
        runner.assert.equals(nil, random.bytes(0, true))
        runner.assert.equals(nil, random.bytes(-1, true))
        runner.assert.equals(nil, random.bytes(1.5, true))
        runner.assert.equals(nil, random.bytes("32", true))
    end)
end)
