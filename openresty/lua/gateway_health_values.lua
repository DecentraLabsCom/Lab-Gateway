-- Pure value and status helpers used by gateway_health.lua.
--
-- Keeping these functions free of ngx, filesystem, network and OpenResty
-- state makes the health policy independently testable without changing the
-- response assembled by the gateway endpoint.

local _M = {}

local CERTIFICATE_MONTHS = {
    Jan = 1, Feb = 2, Mar = 3, Apr = 4, May = 5, Jun = 6,
    Jul = 7, Aug = 8, Sep = 9, Oct = 10, Nov = 11, Dec = 12
}

function _M.response_is_reachable(status, body)
    if not status then
        return false
    end
    if status < 500 then
        return true
    end
    if type(body) ~= "table" then
        return false
    end
    local payload_status = tostring(body.status or ""):upper()
    return payload_status == "DEGRADED"
        or payload_status == "PARTIAL"
        or body.db ~= nil
        or body.guacamole_schema ~= nil
end

function _M.capture_result(response, parsed_body, raw_body)
    if not response then
        return { ok = false, error = "no response" }
    end
    return {
        status = response.status,
        ok = response.status and response.status < 400,
        reachable = _M.response_is_reachable(response.status, parsed_body),
        body = parsed_body,
        raw = raw_body
    }
end

function _M.trim(value)
    if not value then
        return ""
    end
    return (tostring(value):gsub("^%s*(.-)%s*$", "%1"))
end

function _M.normalize_issuer(value)
    local normalized = _M.trim(value)
    if normalized == "" then
        return ""
    end
    return normalized:gsub("/+$", "")
end

function _M.lite_mode_enabled(value)
    return value == 1 or value == true or value == "1"
end

function _M.build_local_issuer(server_name, https_port)
    local normalized_server_name = _M.trim(server_name or "localhost")
    local normalized_https_port = _M.trim(https_port or "443")
    local port_segment = ""
    if normalized_https_port ~= "" and normalized_https_port ~= "443" then
        port_segment = ":" .. normalized_https_port
    end
    return string.format("https://%s%s/auth", normalized_server_name, port_segment)
end

function _M.looks_like_public_key_pem(value)
    if type(value) ~= "string" then
        return false
    end
    return value:find("BEGIN PUBLIC KEY", 1, true) ~= nil
        and value:find("END PUBLIC KEY", 1, true) ~= nil
end

function _M.canonical_public_key(value)
    if not _M.looks_like_public_key_pem(value) then
        return nil
    end
    local body = value:match("%-%-%-%-%-BEGIN PUBLIC KEY%-%-%-%-%-(.-)%-%-%-%-%-END PUBLIC KEY%-%-%-%-%-")
    if not body then
        return nil
    end
    return body:gsub("%s+", "")
end

function _M.parse_issuer_url(value)
    local raw = _M.trim(value)
    if raw == "" then
        return nil
    end
    local scheme, host, port = raw:match("^(https?)://([^/:]+):?(%d*)")
    if not scheme or not host then
        return nil
    end
    local port_num = tonumber(port)
    if not port_num then
        port_num = (scheme == "https") and 443 or 80
    end
    return {
        scheme = scheme,
        host = host,
        port = port_num
    }
end

function _M.issuer_origin(parsed)
    if not parsed then
        return nil
    end
    local default_port = parsed.scheme == "https" and 443 or 80
    local suffix = ""
    if parsed.port ~= default_port then
        suffix = ":" .. tostring(parsed.port)
    end
    return string.format("%s://%s%s", parsed.scheme, parsed.host, suffix)
end

function _M.blockchain_ready(check)
    if not check or not check.status then
        return false
    end
    return check.status >= 200 and check.status < 400
end

function _M.certificate_days_remaining(not_after, now, parse_http_time)
    local normalized = _M.trim(not_after)
    if normalized == "" then
        return nil
    end

    local timestamp = parse_http_time and parse_http_time(normalized) or nil
    if not timestamp then
        local mon, day, hour, min, sec, year = normalized:match(
            "^(%a+)%s+(%d+)%s+(%d+):(%d+):(%d+)%s+(%d+)%s+GMT$"
        )
        local month_num = mon and CERTIFICATE_MONTHS[mon] or nil
        local year_num = year and tonumber(year) or nil
        local day_num = day and tonumber(day) or nil
        local hour_num = hour and tonumber(hour) or nil
        local min_num = min and tonumber(min) or nil
        local sec_num = sec and tonumber(sec) or nil

        if month_num and year_num and day_num and hour_num and min_num and sec_num then
            local local_ts = os.time({
                year = year_num,
                month = month_num,
                day = day_num,
                hour = hour_num,
                min = min_num,
                sec = sec_num
            })
            if local_ts then
                local local_date = os.date("*t", local_ts)
                local utc_date = os.date("!*t", local_ts)
                local offset = os.difftime(
                    type(local_date) == "table" and os.time(local_date) or local_ts,
                    type(utc_date) == "table" and os.time(utc_date) or local_ts
                )
                timestamp = local_ts - offset
            end
        end
    end

    if not timestamp or not now then
        return nil
    end
    return math.floor((timestamp - now) / 86400)
end

function _M.overall_status(services)
    local ok_count = 0
    local reachable_count = 0
    for _, svc in ipairs(services) do
        if svc.ok then ok_count = ok_count + 1 end
        if svc.reachable then reachable_count = reachable_count + 1 end
    end
    if ok_count == #services then return "UP" end
    if ok_count > 0 or reachable_count > 0 then return "PARTIAL" end
    return "DOWN"
end

function _M.build_status_checks(context)
    local status_checks = {
        { ok = context.guac_ok, reachable = context.guac_reachable },
        { ok = context.guac_api_ok, reachable = context.guac_api_reachable },
        { ok = context.guacd_ok, reachable = context.guacd_ok },
        { ok = context.ops_ok, reachable = context.ops_reachable },
        { ok = context.guacamole_schema_ok, reachable = context.ops_reachable },
        { ok = context.mysql_ok, reachable = context.mysql_ok or context.ops_reachable }
    }

    if not context.lite_mode then
        table.insert(status_checks, 1, {
            ok = context.blockchain_ok,
            reachable = context.blockchain_reachable
        })
    elseif context.lite_auth then
        table.insert(status_checks, {
            ok = context.lite_auth.ok,
            reachable = context.lite_auth.issuer_host_dns_ok
        })
    end
    if context.fmu_runner_enabled then
        table.insert(status_checks, {
            ok = context.fmu_runner_ok,
            reachable = context.fmu_runner_reachable
        })
    end
    if context.aas_enabled then
        table.insert(status_checks, {
            ok = context.aas_ok,
            reachable = context.aas_reachable
        })
    end
    return status_checks
end

function _M.build_result(context)
    local lite_auth = context.lite_auth
    return {
        mode = context.lite_mode and "lite" or "full",
        lite = context.lite_mode,
        status = context.gateway_status,
        demo = context.demo,
        services = {
            blockchain = {
                ok = context.blockchain_ok,
                reachable = context.blockchain_reachable,
                status = context.blockchain.status,
                required = not context.lite_mode,
                details = context.block_body
            },
            guacamole = {
                ok = context.guac.ok,
                status = context.guac.status
            },
            guacamole_api = {
                ok = context.guac_api_ok,
                status = context.guac_api.status
            },
            guacd = {
                ok = context.guacd_ok or false,
                status = context.guacd_ok and "OK" or context.guacd_err
            },
            ops = {
                ok = context.ops.ok,
                status = context.ops.status,
                hosts = context.ops_body.hosts or context.ops_body.host_count,
                poll_enabled = context.ops_body.polling_enabled or context.ops_body.polling,
                demo = context.ops_body.demo
            },
            demo = context.demo,
            guacamole_schema = {
                ok = context.guacamole_schema_ok,
                checked_by = "ops-worker"
            },
            mysql = {
                ok = context.mysql_ok or false
            },
            lite_auth = {
                ok = lite_auth and lite_auth.ok or (not context.lite_mode),
                issuer = lite_auth and lite_auth.issuer or context.configured_issuer,
                local_issuer = lite_auth and lite_auth.local_issuer or context.local_issuer,
                external_issuer = lite_auth and lite_auth.external_issuer or false,
                issuer_url_valid = lite_auth and lite_auth.issuer_url_valid or false,
                issuer_host_dns_ok = lite_auth and lite_auth.issuer_host_dns_ok or false,
                active_public_key_source = lite_auth and lite_auth.active_public_key_source or nil,
                local_public_key_present = lite_auth and lite_auth.local_public_key_present
                    or context.public_key_file_present,
                local_public_key_valid = lite_auth and lite_auth.local_public_key_valid or false,
                remote_public_key_ok = lite_auth and lite_auth.remote_public_key_ok or false,
                public_key_matches = lite_auth and lite_auth.public_key_matches or false,
                remote_public_key_status = lite_auth and lite_auth.remote_public_key_status
                    or "not_applicable"
            },
            fmu_runner = {
                ok = context.fmu_runner_ok,
                enabled = context.fmu_runner_enabled,
                status = context.fmu_runner_status,
                details = context.fmu_runner_body
            },
            aas = {
                ok = context.aas.ok,
                enabled = context.aas_enabled,
                status = context.aas.status
            }
        },
        infra = {
            dns = context.dns,
            mysql_up = context.mysql_ok or false,
            cert = {
                days_remaining = context.cert_days,
                fullchain_present = context.fullchain_present,
                privkey_present = context.privkey_present
            },
            static_root_ok = context.static_root_ok,
            env = context.env_ok
        },
        version = context.block_body.version
    }
end

return _M
