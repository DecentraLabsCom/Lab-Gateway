-- Public health responses deliberately contain only an aggregate status.
-- Detailed backend, DNS, key and queue diagnostics live behind the
-- lab-manager guard at /health/details and /gateway/health/details.

local cjson = require "cjson.safe"

local function probe(path)
    local response = ngx.location.capture(path)
    -- A health probe only needs to distinguish an unavailable upstream from
    -- one that is reachable but requires a method/body/authentication.
    if not response or not response.status then
        return "DOWN"
    end
    if response.status < 500 then
        return "UP"
    end

    -- The backend deliberately returns HTTP 503 when it is reachable but its
    -- operational configuration is incomplete (for example, before the
    -- institution is registered as provider or consumer). Keep that distinct
    -- from an upstream that could not be reached at all.
    local body = cjson.decode(response.body or "")
    local backend_status = type(body) == "table" and tostring(body.status or ""):upper() or ""
    if backend_status == "DEGRADED" or backend_status == "PARTIAL" then
        return "PARTIAL"
    end
    return "DOWN"
end

local function aggregate_gateway_status(checks)
    local has_up = false
    local has_partial = false
    local has_down = false

    for _, status in ipairs(checks) do
        if status == "UP" then
            has_up = true
        elseif status == "PARTIAL" then
            has_partial = true
        else
            has_down = true
        end
    end

    if not has_down and not has_partial then
        return "UP"
    end
    if has_up or has_partial then
        return "PARTIAL"
    end
    return "DOWN"
end

local uri = ngx.var.uri or "/health"
local config = ngx.shared and ngx.shared.config
local lite_mode = config and config:get("lite_mode")
lite_mode = lite_mode == 1 or lite_mode == true or lite_mode == "1"

local service = "lab-gateway"
local status = "UP"

if uri == "/ops/health" then
    service = "ops-worker"
    status = probe("/__health_ops")
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
    status = aggregate_gateway_status(checks)
end

local result = {
    status = status,
    service = service,
    mode = lite_mode and "lite" or "full",
    public = true
}

ngx.header["Content-Type"] = "application/json"
ngx.header["Cache-Control"] = "no-store"
ngx.status = status == "UP" and 200 or 503
ngx.say(cjson.encode(result))
