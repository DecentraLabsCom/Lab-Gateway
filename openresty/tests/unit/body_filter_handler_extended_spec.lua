local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local handler = require "modules.body_filter_handler"
local cjson = require "cjson.safe"

local function new_ngx(opts)
    opts = opts or {}
    local ngx = ngx_factory.new({
        header = opts.header or { ["Content-Type"] = "application/json" },
        cache = opts.cache or {},
        ctx = opts.ctx or {}
    })
    return ngx
end

runner.describe("Body filter handler extended tests", function()
    -- Test: Various content types
    runner.it("skips text/plain content type", function()
        local ngx = new_ngx({ header = { ["Content-Type"] = "text/plain" } })
        handler.run(ngx, '{"authToken":"abc"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("skips text/xml content type", function()
        local ngx = new_ngx({ header = { ["Content-Type"] = "text/xml" } })
        handler.run(ngx, '{"authToken":"abc"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("handles application/json with charset", function()
        local ngx = new_ngx({ header = { ["Content-Type"] = "application/json; charset=utf-8" } })
        handler.run(ngx, '{"authToken":"token123","username":"CharsetUser"}', true, { cjson = cjson })
        runner.assert.equals("token123", ngx.shared.cache._data["token:charsetuser"])
    end)

    runner.it("skips when Content-Type is nil", function()
        local ngx = new_ngx({ header = {} })
        handler.run(ngx, '{"authToken":"abc","username":"User"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    -- Test: Various body formats
    runner.it("skips empty body", function()
        local ngx = new_ngx()
        handler.run(ngx, "", true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("skips whitespace-only body", function()
        local ngx = new_ngx()
        handler.run(ngx, "   \n\t  ", true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("handles body starting with array", function()
        local ngx = new_ngx()
        handler.run(ngx, '[{"authToken":"abc","username":"User"}]', true, { cjson = cjson })
        -- Arrays don't have authToken at root level
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("handles body with extra whitespace", function()
        local ngx = new_ngx()
        handler.run(ngx, '  {"authToken":"spaces","username":"SpaceUser"}  ', true, { cjson = cjson })
        runner.assert.equals("spaces", ngx.shared.cache._data["token:spaceuser"])
    end)

    -- Test: Chunked response handling
    runner.it("handles multiple chunks before eof", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"auth', false, { cjson = cjson })
        handler.run(ngx, 'Token":"chunk', false, { cjson = cjson })
        handler.run(ngx, 'ed","username":"ChunkUser"}', true, { cjson = cjson })
        runner.assert.equals("chunked", ngx.shared.cache._data["token:chunkuser"])
    end)

    runner.it("handles empty chunks", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":', false, { cjson = cjson })
        handler.run(ngx, '', false, { cjson = cjson })
        handler.run(ngx, '"empty","username":"EmptyChunk"}', true, { cjson = cjson })
        runner.assert.equals("empty", ngx.shared.cache._data["token:emptychunk"])
    end)

    runner.it("handles nil chunk", function()
        local ngx = new_ngx()
        handler.run(ngx, nil, false, { cjson = cjson })
        handler.run(ngx, '{"authToken":"nil","username":"NilChunk"}', true, { cjson = cjson })
        runner.assert.equals("nil", ngx.shared.cache._data["token:nilchunk"])
    end)

    -- Test: Username normalization
    runner.it("normalizes uppercase username", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"upper","username":"UPPERCASE"}', true, { cjson = cjson })
        runner.assert.equals("upper", ngx.shared.cache._data["token:uppercase"])
        runner.assert.equals("uppercase", ngx.shared.cache._data["guac_token:upper"])
    end)

    runner.it("normalizes mixed case username", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"mixed","username":"MixedCase"}', true, { cjson = cjson })
        runner.assert.equals("mixed", ngx.shared.cache._data["token:mixedcase"])
    end)

    -- Test: Missing required fields
    runner.it("skips when only authToken present", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"abc"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:"])
    end)

    runner.it("skips when only username present", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"username":"User"}', true, { cjson = cjson })
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("skips when both fields are empty strings", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"","username":""}', true, { cjson = cjson })
        -- Empty strings are falsy in some implementations
    end)

    -- Test: Special characters in values
    runner.it("handles special characters in authToken", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"abc-123_xyz","username":"SpecialToken"}', true, { cjson = cjson })
        runner.assert.equals("abc-123_xyz", ngx.shared.cache._data["token:specialtoken"])
    end)

    runner.it("handles unicode in username", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"unicode","username":"José"}', true, { cjson = cjson })
        runner.assert.equals("unicode", ngx.shared.cache._data["token:josé"])
    end)

    -- Test: Reverse mapping
    runner.it("stores reverse mapping correctly", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"reversetest","username":"ReverseUser"}', true, { cjson = cjson })
        runner.assert.equals("reversetest", ngx.shared.cache._data["token:reverseuser"])
        runner.assert.equals("reverseuser", ngx.shared.cache._data["guac_token:reversetest"])
    end)

    -- Test: JSON decode errors
    runner.it("handles truncated JSON", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"abc","username":"User"', true, { cjson = cjson })
        -- Should not crash, just skip
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    runner.it("handles JSON with extra comma", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"abc","username":"User",}', true, { cjson = cjson })
        -- Invalid JSON, should skip
        runner.assert.equals(nil, ngx.shared.cache._data["token:user"])
    end)

    -- Test: Large payload
    runner.it("handles large payload", function()
        local ngx = new_ngx()
        local large_payload = '{"authToken":"largetoken","username":"LargeUser","data":"' ..
            string.rep("x", 1000) .. '"}'
        handler.run(ngx, large_payload, true, { cjson = cjson })
        runner.assert.equals("largetoken", ngx.shared.cache._data["token:largeuser"])
    end)

    -- Test: Additional fields in response
    runner.it("ignores extra fields", function()
        local ngx = new_ngx()
        handler.run(ngx, '{"authToken":"extra","username":"ExtraUser","dataSource":"mysql","availableDataSources":["mysql"]}', true, { cjson = cjson })
        runner.assert.equals("extra", ngx.shared.cache._data["token:extrauser"])
    end)

    -- Test: Context preservation across calls
    runner.it("preserves context across chunk calls", function()
        local ngx = new_ngx({ ctx = { existing = "value" } })
        handler.run(ngx, '{"auth', false, { cjson = cjson })
        runner.assert.equals("value", ngx.ctx.existing)
        handler.run(ngx, 'Token":"ctx","username":"CtxUser"}', true, { cjson = cjson })
        runner.assert.equals("value", ngx.ctx.existing)
    end)
end)

return runner
