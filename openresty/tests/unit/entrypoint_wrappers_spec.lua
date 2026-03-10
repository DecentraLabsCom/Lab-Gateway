local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_lua_path(name)
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lua/" .. name,
        dir .. "/../lua/" .. name,
        "openresty/lua/" .. name,
        "lua/" .. name
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate " .. name .. " for tests")
end

local function with_stubbed_module(name, module, fn)
    local previous_loaded = package.loaded[name]
    local previous_preload = package.preload[name]
    package.loaded[name] = nil
    package.preload[name] = function()
        return module
    end

    local ok, result = xpcall(fn, debug.traceback)

    package.preload[name] = previous_preload
    package.loaded[name] = previous_loaded

    if not ok then
        error(result, 0)
    end

    return result
end

local function run_entrypoint(name, ngx)
    local previous_ngx = _G.ngx
    _G.ngx = ngx

    local ok, result = xpcall(function()
        dofile(resolve_lua_path(name))
    end, debug.traceback)

    _G.ngx = previous_ngx

    if not ok then
        error(result, 0)
    end

    return result
end

runner.describe("OpenResty entrypoint wrappers", function()
    runner.it("delegates access phase to modules.access_handler", function()
        local captured = {}
        local ngx = ngx_factory.new()

        with_stubbed_module("modules.access_handler", {
            run = function(passed_ngx)
                captured.ngx = passed_ngx
            end
        }, function()
            run_entrypoint("access.lua", ngx)
        end)

        runner.assert.equals(ngx, captured.ngx)
    end)

    runner.it("forwards body chunks and EOF flag to modules.body_filter_handler", function()
        local captured = {}
        local ngx = ngx_factory.new()
        ngx.arg = { "{\"type\":\"token\"}", true }

        with_stubbed_module("modules.body_filter_handler", {
            run = function(passed_ngx, chunk, eof)
                captured.ngx = passed_ngx
                captured.chunk = chunk
                captured.eof = eof
            end
        }, function()
            run_entrypoint("body_filter.lua", ngx)
        end)

        runner.assert.equals(ngx, captured.ngx)
        runner.assert.equals("{\"type\":\"token\"}", captured.chunk)
        runner.assert.equals(true, captured.eof)
    end)

    runner.it("delegates header filtering to modules.header_filter_handler", function()
        local captured = {}
        local ngx = ngx_factory.new()

        with_stubbed_module("modules.header_filter_handler", {
            run = function(passed_ngx)
                captured.ngx = passed_ngx
            end
        }, function()
            run_entrypoint("header_filter.lua", ngx)
        end)

        runner.assert.equals(ngx, captured.ngx)
    end)

    runner.it("delegates log phase to modules.log_handler", function()
        local captured = {}
        local ngx = ngx_factory.new()

        with_stubbed_module("modules.log_handler", {
            run = function(passed_ngx)
                captured.ngx = passed_ngx
            end
        }, function()
            run_entrypoint("log.lua", ngx)
        end)

        runner.assert.equals(ngx, captured.ngx)
    end)

    runner.it("starts the session guard during worker initialization", function()
        local constructed = 0
        local started = 0

        with_stubbed_module("modules.session_guard", {
            new = function()
                constructed = constructed + 1
                return {
                    start = function()
                        started = started + 1
                    end
                }
            end
        }, function()
            run_entrypoint("init_worker.lua", ngx_factory.new())
        end)

        runner.assert.equals(1, constructed)
        runner.assert.equals(1, started)
    end)
end)

return runner
