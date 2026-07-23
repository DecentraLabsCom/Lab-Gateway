local cjson = require "cjson.safe"
local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_public_health_path()
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."
    local candidates = {
        dir .. "/../../lua/public_health.lua",
        dir .. "/../lua/public_health.lua",
        "openresty/lua/public_health.lua",
        "lua/public_health.lua"
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate public_health.lua for tests")
end

local function run_health(uri, captures, config)
    local ngx = ngx_factory.new({
        var = { uri = uri },
        config = config or {},
        location_capture = function(path)
            return captures[path]
        end
    })
    local previous_ngx = _G.ngx
    _G.ngx = ngx
    local ok, err = xpcall(function()
        dofile(resolve_public_health_path())
    end, debug.traceback)
    _G.ngx = previous_ngx
    if not ok then
        error(err, 0)
    end
    return ngx, cjson.decode(ngx._say_output[1])
end

runner.describe("OpenResty public_health.lua", function()
    runner.it("reports UP when optional services are reachable with non-2xx responses", function()
        local ngx, result = run_health("/gateway/health", {
            ["/__health_guacamole"] = { status = 200 },
            ["/__health_guac_api"] = { status = 405 },
            ["/__health_ops"] = { status = 200 },
            ["/__health_blockchain"] = { status = 200 },
            ["/__health_fmu_runner"] = { status = 404 },
            ["/__health_aas"] = { status = 200 }
        }, {
            fmu_runner_enabled = 1,
            aas_enabled = 1
        })

        runner.assert.equals(200, ngx.status)
        runner.assert.equals("UP", result.status)
        runner.assert.equals("full", result.mode)
    end)

    runner.it("reports PARTIAL when one dependency is unavailable but others are healthy", function()
        local ngx, result = run_health("/gateway/health", {
            ["/__health_guacamole"] = { status = 503 },
            ["/__health_guac_api"] = { status = 200 },
            ["/__health_ops"] = { status = 200 },
            ["/__health_blockchain"] = { status = 200 }
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals("PARTIAL", result.status)
    end)

    runner.it("reports DOWN when all gateway dependencies are unavailable", function()
        local ngx, result = run_health("/gateway/health", {
            ["/__health_guacamole"] = { status = 503 },
            ["/__health_guac_api"] = { status = 503 },
            ["/__health_ops"] = { status = 503 },
            ["/__health_blockchain"] = { status = 503 }
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals("DOWN", result.status)
    end)

    runner.it("reports PARTIAL when the backend is reachable but its health is degraded", function()
        local ngx, result = run_health("/gateway/health", {
            ["/__health_guacamole"] = { status = 200 },
            ["/__health_guac_api"] = { status = 200 },
            ["/__health_ops"] = { status = 200 },
            ["/__health_blockchain"] = {
                status = 503,
                body = '{"status":"DEGRADED","provider_registered":false,"consumer_registered":false}'
            }
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals("PARTIAL", result.status)
    end)

    runner.it("reports the ops-worker health status independently", function()
        local ngx, result = run_health("/ops/health", {
            ["/__health_ops"] = { status = 500 }
        })

        runner.assert.equals(503, ngx.status)
        runner.assert.equals("ops-worker", result.service)
        runner.assert.equals("DOWN", result.status)
    end)

    runner.it("skips Full-only checks in Lite mode", function()
        local ngx, result = run_health("/gateway/health", {
            ["/__health_guacamole"] = { status = 200 },
            ["/__health_guac_api"] = { status = 404 },
            ["/__health_ops"] = { status = 200 }
        }, { lite_mode = 1 })

        runner.assert.equals(200, ngx.status)
        runner.assert.equals("lite", result.mode)
        runner.assert.equals("UP", result.status)
    end)

    runner.it("reports the default gateway health without dependency probes", function()
        local ngx, result = run_health("/health", {})

        runner.assert.equals(200, ngx.status)
        runner.assert.equals("lab-gateway", result.service)
        runner.assert.equals("UP", result.status)
    end)
end)

return runner
