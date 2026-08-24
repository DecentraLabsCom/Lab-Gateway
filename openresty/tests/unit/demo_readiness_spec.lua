local runner = require "tests.helpers.runner"

local function resolve_lua_path(name)
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."
    local candidates = {
        dir .. "/../../lua/" .. name,
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
    error("Cannot locate " .. name)
end

local MODULE_PATH = resolve_lua_path("demo_readiness.lua")

local function with_module_stubs(stubs, fn)
    local previous_loaded = {}
    local previous_preload = {}
    for name, module in pairs(stubs) do
        previous_loaded[name] = package.loaded[name]
        previous_preload[name] = package.preload[name]
        package.loaded[name] = nil
        package.preload[name] = function() return module end
    end
    local ok, result = xpcall(fn, debug.traceback)
    for name in pairs(stubs) do
        package.loaded[name] = previous_loaded[name]
        package.preload[name] = previous_preload[name]
    end
    if not ok then error(result, 0) end
    return result
end

local function load_module()
    return with_module_stubs({
        ["cjson.safe"] = {
            decode = function(value) return value end
        },
        ["resty.http"] = {}
    }, function()
        package.loaded["demo_readiness"] = nil
        return dofile(MODULE_PATH)
    end)
end

local function configured_context(overrides)
    local context = {
        config = {
            demo_lab_id = "42",
            demo_connection_id = "7",
            demo_user = "demo",
            marketplace_url = "https://marketplace.example"
        },
        core_ready = true,
        now = 100,
        ops_demo = {
            status = "ready",
            checks = {
                connection = true,
                principal = true,
                permission = true,
                physical_host = true
            }
        },
        marketplace_probe = function()
            return {
                ok = true,
                eligible = true,
                lab_id = "42",
                start = "105",
                finish = "135"
            }
        end
    }
    for key, value in pairs(overrides or {}) do context[key] = value end
    return context
end

runner.describe("Demo readiness", function()
    runner.it("returns ready only when gateway, operator checks and Marketplace agree", function()
        local module = load_module()
        local result = module.evaluate(configured_context())
        runner.assert.equals("ready", result.status)
        runner.assert.equals(true, result.enabled)
        runner.assert.equals(true, result.checks.marketplace)
        runner.assert.equals(true, result.checks.gateway)
    end)

    runner.it("returns disabled when no demo binding is configured", function()
        local module = load_module()
        local result = module.evaluate({ config = {}, core_ready = true })
        runner.assert.equals("disabled", result.status)
        runner.assert.equals(false, result.enabled)
    end)

    runner.it("returns misconfigured when only one binding identifier is present", function()
        local module = load_module()
        local result = module.evaluate({
            config = { demo_lab_id = "42", demo_user = "demo", marketplace_url = "https://marketplace.example" },
            core_ready = true
        })
        runner.assert.equals("misconfigured", result.status)
    end)

    runner.it("returns busy when the physical station or Marketplace slot is occupied", function()
        local module = load_module()
        local result = module.evaluate(configured_context({
            ops_demo = { status = "busy", checks = { physical_host = false } }
        }))
        runner.assert.equals("busy", result.status)
    end)
end)

return runner
