local _M = {}

local function increment(dict, key)
    if dict then
        dict:incr(key, 1, 0)
    end
end

local function deliver(payload, deps)
    if deps and deps.deliver then
        return deps.deliver(payload)
    end
    local token = os.getenv("SESSION_OBSERVATION_INGEST_TOKEN") or ""
    if token == "" then
        return false, "SESSION_OBSERVATION_INGEST_TOKEN is not configured"
    end
    local http = require "resty.http"
    local cjson = require "cjson.safe"
    local httpc = http.new()
    httpc:set_timeout(1500)
    local res, err = httpc:request_uri(
        os.getenv("OPS_GUACAMOLE_TOKEN_INGEST_URL")
            or "http://ops-worker:8081/internal/guacamole-token-revocations",
        {
            method = "POST",
            body = cjson.encode(payload),
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Gateway-Observation-Token"] = token,
            },
        }
    )
    if not res or res.status < 200 or res.status >= 300 then
        return false, err or (res and ("status " .. res.status) or "no response")
    end
    httpc:set_keepalive(10000, 5)
    return true
end

-- The Ops endpoint persists the token encrypted before returning 202. Keeping
-- this operation synchronous lets the response filter withhold the Guacamole
-- token unless its future revocation is durably registered.
function _M.schedule(ngx_ctx, payload, deps)
    local ngx = ngx_ctx or ngx
    local delivered, err = deliver(payload, deps)
    if delivered then
        increment(ngx.shared.cache, "metric:guac_revocation_ingest_success")
        return true
    end
    increment(ngx.shared.cache, "metric:guac_revocation_ingest_failure")
    ngx.log(ngx.ERR, "Guacamole revocation registration failed: " .. tostring(err))
    return false
end

return _M
