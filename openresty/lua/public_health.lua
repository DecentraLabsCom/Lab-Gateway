-- Public health responses deliberately contain only an aggregate status.
-- Detailed backend, DNS, key and queue diagnostics live behind the
-- lab-manager guard at /health/details and /gateway/health/details.

local cjson = require "cjson.safe"

local function probe(path)
    local response = ngx.location.capture(path)
    return response and response.status and response.status < 400
end

local uri = ngx.var.uri or "/health"
local config = ngx.shared and ngx.shared.config
local lite_mode = config and config:get("lite_mode")
lite_mode = lite_mode == 1 or lite_mode == true or lite_mode == "1"

local service = "lab-gateway"
local ready = true

if uri == "/ops/health" then
    service = "ops-worker"
    ready = probe("/__health_ops")
elseif uri == "/gateway/health" then
    local checks = {
        probe("/__health_guacamole"),
        probe("/__health_guac_api"),
        probe("/__health_ops")
    }
    if not lite_mode then
        checks[#checks + 1] = probe("/__health_blockchain")
    end
    if config and config:get("fmu_runner_enabled") == 1 then
        checks[#checks + 1] = probe("/__health_fmu_runner")
    end
    if config and config:get("aas_enabled") == 1 then
        checks[#checks + 1] = probe("/__health_aas")
    end
    for _, ok in ipairs(checks) do
        if not ok then
            ready = false
            break
        end
    end
end

local result = {
    status = ready and "UP" or "DOWN",
    service = service,
    mode = lite_mode and "lite" or "full",
    public = true
}

ngx.header["Content-Type"] = "application/json"
ngx.header["Cache-Control"] = "no-store"
ngx.status = ready and 200 or 503
ngx.say(cjson.encode(result))
