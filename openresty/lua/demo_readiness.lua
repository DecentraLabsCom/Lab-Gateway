-- Demo readiness is deliberately fail-closed.  A configured demo is usable
-- only when the local binding, Guacamole principal, physical Station,
-- Marketplace authority and gateway access plane all agree.
local cjson = require "cjson.safe"

local M = {}

local function trim(value)
    if value == nil then return "" end
    return (tostring(value):gsub("^%s*(.-)%s*$", "%1"))
end

local function config_value(config, key)
    if config and config.get then
        return config:get(key)
    end
    if type(config) == "table" then
        return config[key]
    end
    return nil
end

local function canonical_decimal(value, positive)
    local normalized = trim(value)
    if not normalized:match("^%d+$") then return nil end
    normalized = normalized:gsub("^0+", "")
    if normalized == "" then normalized = "0" end
    if positive and normalized == "0" then return nil end
    return normalized
end

local function valid_user(value)
    local normalized = trim(value)
    return #normalized >= 1 and #normalized <= 128
        and normalized:match("^[A-Za-z0-9_.%-]+$") ~= nil
end

local function all_true(checks)
    for _, value in pairs(checks) do
        if value ~= true then return false end
    end
    return true
end

local function build_marketplace_probe(http_module, url, lab_id, now)
    if not http_module or not http_module.new then
        return function() return { ok = false, error = "http client unavailable" } end
    end

    return function()
        local start = math.floor(tonumber(now) or 0) + 5
        local finish = start + 30
        local endpoint = url .. "/api/demo/eligibility?labId=" .. lab_id
            .. "&start=" .. tostring(start) .. "&end=" .. tostring(finish)
        local httpc = http_module.new()
        httpc:set_timeout(2000)
        local response, err = httpc:request_uri(endpoint, {
            method = "GET",
            ssl_verify = true,
            headers = { ["Accept"] = "application/json" }
        })
        if not response then
            return { ok = false, error = err or "Marketplace request failed" }
        end
        if response.status ~= 200 then
            return { ok = false, error = "Marketplace returned HTTP " .. tostring(response.status) }
        end
        local payload = cjson.decode(response.body or "")
        if type(payload) ~= "table"
            or type(payload.eligible) ~= "boolean"
            or trim(payload.labId) ~= lab_id
            or trim(payload.start) ~= tostring(start)
            or trim(payload["end"]) ~= tostring(finish) then
            return { ok = false, error = "Marketplace eligibility response failed validation" }
        end
        return {
            ok = true,
            eligible = payload.eligible,
            lab_id = lab_id,
            start = tostring(start),
            ["end"] = tostring(finish)
        }
    end
end

function M.evaluate(options)
    options = options or {}
    local config = options.config or {}
    local lab_id = canonical_decimal(config_value(config, "demo_lab_id"), false)
    local connection_id = canonical_decimal(config_value(config, "demo_connection_id"), true)
    local raw_lab_id = trim(config_value(config, "demo_lab_id"))
    local raw_connection_id = trim(config_value(config, "demo_connection_id"))
    local user = trim(config_value(config, "demo_user"))
    if user == "" then user = "demo-lab-disabled" end
    local marketplace_url = trim(config_value(config, "marketplace_url")):gsub("/+$", "")

    local result = {
        enabled = raw_lab_id ~= "" or raw_connection_id ~= "",
        status = "disabled",
        labId = lab_id,
        connectionId = connection_id,
        user = user,
        checks = {
            configuration = false,
            connection = false,
            principal = false,
            permission = false,
            physical_host = false,
            marketplace = false,
            gateway = false
        }
    }

    if not result.enabled then
        return result
    end

    if not lab_id or not connection_id or not valid_user(user)
        or not marketplace_url:match("^https?://") then
        result.status = "misconfigured"
        return result
    end
    result.checks.configuration = true

    local ops_demo = options.ops_demo
    if not ops_demo and options.ops and options.ops.body then
        ops_demo = options.ops.body.demo
    end
    if type(ops_demo) ~= "table" then
        result.status = "unready"
        return result
    end

    local ops_checks = ops_demo.checks or {}
    result.checks.connection = ops_checks.connection == true
    result.checks.principal = ops_checks.principal == true
    result.checks.permission = ops_checks.permission == true
    result.checks.physical_host = ops_checks.physical_host == true

    local ops_status = trim(ops_demo.status):lower()
    if ops_status == "misconfigured" then
        result.status = "misconfigured"
        return result
    end
    if ops_status == "busy" then
        result.status = "busy"
        return result
    end
    if ops_status ~= "ready" then
        result.status = "unready"
        return result
    end

    result.checks.gateway = options.core_ready == true
    if not result.checks.gateway or not all_true({
        result.checks.connection,
        result.checks.principal,
        result.checks.permission,
        result.checks.physical_host
    }) then
        result.status = "unready"
        return result
    end

    local probe = options.marketplace_probe
    if not probe then
        local ok_http, resty_http = pcall(require, "resty.http")
        probe = build_marketplace_probe(
            ok_http and resty_http or nil,
            marketplace_url,
            lab_id,
            options.now or (ngx and ngx.time and ngx.time() or 0)
        )
    end
    local authority = probe()
    result.marketplace = authority
    if not authority or authority.ok ~= true then
        result.status = "unready"
        return result
    end
    result.checks.marketplace = authority.eligible == true
    if not result.checks.marketplace then
        result.status = "busy"
        return result
    end

    result.status = "ready"
    return result
end

return M
