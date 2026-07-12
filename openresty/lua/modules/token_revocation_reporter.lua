local _M = {}

local MAX_DELIVERY_ATTEMPTS = 3
local RETRY_DELAYS_SECONDS = { 0.1, 0.5 }

local function persist(payload, deps, ngx_ctx)
    if deps and deps.persist then
        return deps.persist(payload)
    end
    local cjson = require "cjson.safe"
    local directory = os.getenv("GUAC_REVOCATION_SPOOL_DIR") or "/var/spool/guac-revocations"
    local digest = ngx_ctx.md5(payload.authToken)
    local final_path = directory .. "/" .. digest .. ".json"
    local temporary_path = final_path .. ".tmp"
    local file, open_error = io.open(temporary_path, "w")
    if not file then
        return false, open_error
    end
    local encoded = cjson.encode(payload)
    if not encoded then
        file:close()
        os.remove(temporary_path)
        return false, "unable to encode revocation record"
    end
    local written, write_error = file:write(encoded)
    if not written then
        file:close()
        os.remove(temporary_path)
        return false, write_error
    end
    file:flush()
    file:close()
    local renamed, rename_error = os.rename(temporary_path, final_path)
    if not renamed then
        os.remove(temporary_path)
        return false, rename_error
    end
    return true, final_path
end

local function remove_persisted(path, deps)
    if deps and deps.remove_persisted then
        return deps.remove_persisted(path)
    end
    return os.remove(path)
end

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

function _M.schedule(ngx_ctx, payload, deps)
    local ngx = ngx_ctx or ngx
    local persisted, spool_path_or_error = persist(payload, deps, ngx)
    if not persisted then
        increment(ngx.shared.cache, "metric:guac_revocation_spool_failure")
        ngx.log(ngx.ERR, "Unable to persist Guacamole revocation registration: " .. tostring(spool_path_or_error))
        return false
    end
    local spool_path = spool_path_or_error
    increment(ngx.shared.cache, "metric:guac_revocation_spool_success")
    local ok, err = ngx.timer.at(0, function(premature)
        if premature then
            return
        end
        local last_error
        for attempt = 1, MAX_DELIVERY_ATTEMPTS do
            local delivered
            delivered, last_error = deliver(payload, deps)
            if delivered then
                remove_persisted(spool_path, deps)
                increment(ngx.shared.cache, "metric:guac_revocation_ingest_success")
                return
            end
            if attempt < MAX_DELIVERY_ATTEMPTS and ngx.sleep then
                ngx.sleep(RETRY_DELAYS_SECONDS[attempt])
            end
        end
        increment(ngx.shared.cache, "metric:guac_revocation_ingest_failure")
        ngx.log(ngx.ERR, "Guacamole revocation registration failed: " .. tostring(last_error))
    end)
    if not ok then
        increment(ngx.shared.cache, "metric:guac_revocation_schedule_failure")
        ngx.log(ngx.ERR, "Unable to schedule Guacamole revocation registration: " .. tostring(err))
        return false
    end
    return true
end

return _M
