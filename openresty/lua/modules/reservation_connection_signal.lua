local ok_http, resty_http = pcall(require, "resty.http")
local cjson = require "cjson.safe"

local _M = {}
local DEFAULT_OPS_API = "http://ops-worker:8081"
local EVENT_PATH = "/api/reservation-connections/event"
local REQUEST_TIMEOUT_MS = 1500

local function trim(value)
    if value == nil then return "" end
    return (tostring(value):gsub("^%s*(.-)%s*$", "%1"))
end

local function ops_base(ngx)
    local config = ngx.shared and ngx.shared.config
    local base = trim(config and config.get and config:get("ops_api_url"))
    if base == "" then base = trim(os.getenv("OPS_API_URL")) end
    if base == "" then base = DEFAULT_OPS_API end
    return base:gsub("/+$", "")
end

function _M.record(ngx, payload)
    if not ok_http or not resty_http then
        return false, "Ops HTTP client unavailable", 503
    end
    local token = trim(os.getenv("OPS_INTERNAL_AUTH_TOKEN"))
    local header = trim(os.getenv("OPS_INTERNAL_AUTH_HEADER"))
    if token == "" then
        return false, "Ops internal authentication is not configured", 503
    end
    if header == "" then header = "X-Ops-Internal-Token" end

    local body, encode_err = cjson.encode(payload)
    if not body then
        return false, encode_err or "Reservation connection event could not be encoded", 503
    end
    local httpc = resty_http.new()
    httpc:set_timeout(REQUEST_TIMEOUT_MS)
    local response, request_err = httpc:request_uri(ops_base(ngx) .. EVENT_PATH, {
        method = "POST",
        body = body,
        headers = {
            ["Content-Type"] = "application/json",
            [header] = token,
        },
    })
    if not response then
        return false, request_err or "Ops Worker did not respond", 503
    end
    local result = cjson.decode(response.body or "") or {}
    if response.status < 200 or response.status >= 300 or result.success ~= true then
        return false, result.error or "Reservation connection event was rejected", response.status
    end
    httpc:set_keepalive(10000, 5)
    return true, result, response.status
end

return _M
