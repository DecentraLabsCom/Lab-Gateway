local cjson = require "cjson.safe"
local resolver = require "resty.dns.resolver"
local ok_http, resty_http = pcall(require, "resty.http")

local PUBLIC_KEY_PATH = "/etc/ssl/private/public_key.pem"
local FULLCHAIN_PATH = "/etc/ssl/private/fullchain.pem"
local PRIVKEY_PATH = "/etc/ssl/private/privkey.pem"
local STATIC_ROOT_INDEX_PATH = "/var/www/html/index.html"

local function trim(value)
    if not value then
        return ""
    end
    return (tostring(value):gsub("^%s*(.-)%s*$", "%1"))
end

local function normalize_issuer(value)
    local normalized = trim(value)
    if normalized == "" then
        return ""
    end
    return normalized:gsub("/+$", "")
end

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

local function read_file(path)
    local f = io.open(path, "r")
    if not f then
        return nil
    end
    local body = f:read("*a")
    f:close()
    return body
end

local function looks_like_public_key_pem(value)
    if type(value) ~= "string" then
        return false
    end
    return value:find("BEGIN PUBLIC KEY", 1, true) ~= nil
        and value:find("END PUBLIC KEY", 1, true) ~= nil
end

local function parse_issuer_url(value)
    local raw = trim(value)
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

local function issuer_origin(parsed)
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

local function is_lite_mode()
    local config = ngx.shared and ngx.shared.config
    local value = config and config:get("lite_mode")
    return value == 1 or value == true or value == "1"
end

local function build_local_issuer()
    local config = ngx.shared and ngx.shared.config
    local server_name = trim((config and config:get("server_name")) or os.getenv("SERVER_NAME") or "localhost")
    local https_port = trim((config and config:get("https_port")) or os.getenv("HTTPS_PORT") or "443")
    local port_segment = ""
    if https_port ~= "" and https_port ~= "443" then
        port_segment = ":" .. https_port
    end
    return string.format("https://%s%s/auth", server_name, port_segment)
end

local function capture(path)
    local res = ngx.location.capture(path)
    if not res then
        return { ok = false, error = "no response" }
    end
    local body = res.body or ""
    local parsed = cjson.decode(body) or {}
    return {
        status = res.status,
        ok = res.status and res.status < 400,
        body = parsed,
        raw = body
    }
end

local function check_dns(host)
    local r, err = resolver:new{ nameservers = { "127.0.0.11" }, retrans = 1, timeout = 100 }
    if not r then
        return false, err
    end
    local ans, qerr = r:query(host)
    if not ans or ans.errcode or not ans[1] or not ans[1].address then
        return false, qerr or (ans and ans.errstr) or "no answer"
    end
    return true
end

local function check_tcp_service(host, port)
    local sock = ngx.socket.tcp()
    sock:settimeouts(100, 100, 100)
    local ok, err = sock:connect(host, port)
    if not ok then
        return false, err
    end
    sock:close()
    return true
end

local function check_mysql()
    return check_tcp_service("mysql", 3306)
end

local function check_guacd()
    return check_tcp_service("guacd", 4822)
end

local function check_guac_schema()
    local ok, mysql = pcall(require, "resty.mysql")
    if not ok then
        return false, "mysql driver missing"
    end
    local user = os.getenv("MYSQL_USER") or ""
    local password = os.getenv("MYSQL_PASSWORD") or ""
    local database = os.getenv("MYSQL_DATABASE") or "guacamole_db"
    if user == "" or password == "" then
        return false, "mysql credentials missing"
    end

    local db, err = mysql:new()
    if not db then
        return false, err
    end
    db:set_timeout(200)

    local ok_conn, err_conn = db:connect({
        host = "mysql",
        port = 3306,
        database = database,
        user = user,
        password = password
    })
    if not ok_conn then
        return false, err_conn
    end

    local res, err_query = db:query("SELECT 1 FROM guacamole_user LIMIT 1")
    db:set_keepalive(10000, 10)
    if not res then
        return false, err_query
    end
    return true
end

local function cert_days_remaining(path)
    local f = io.popen("openssl x509 -enddate -noout -in " .. path .. " 2>/dev/null")
    if not f then return nil end
    local out = f:read("*a") or ""
    f:close()
    local notAfter = out:match("notAfter=([^\r\n]+)")
    if not notAfter then return nil end
    notAfter = notAfter:match("^%s*(.-)%s*$")
    local ts = ngx.parse_http_time(notAfter)
    if not ts then
        local months = {
            Jan = 1, Feb = 2, Mar = 3, Apr = 4, May = 5, Jun = 6,
            Jul = 7, Aug = 8, Sep = 9, Oct = 10, Nov = 11, Dec = 12
        }
        local mon, day, hour, min, sec, year = notAfter:match("^(%a+)%s+(%d+)%s+(%d+):(%d+):(%d+)%s+(%d+)%s+GMT$")
        local month_num = mon and months[mon] or nil
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
                ts = local_ts - offset
            end
        end
    end
    if not ts then return nil end
    local now = ngx.time()
    return math.floor((ts - now) / 86400)
end

local function overall_status(services)
    local ok_count = 0
    for _, svc in ipairs(services) do
        if svc.ok then ok_count = ok_count + 1 end
    end
    if ok_count == #services then return "UP" end
    if ok_count > 0 then return "PARTIAL" end
    return "DOWN"
end

local function check_lite_issuer_trust(issuer)
    local local_public_key = read_file(PUBLIC_KEY_PATH)
    local local_public_key_ok = looks_like_public_key_pem(local_public_key)
    local parsed = parse_issuer_url(issuer)
    local details = {
        issuer = issuer,
        issuer_url_valid = parsed ~= nil,
        local_public_key_present = file_exists(PUBLIC_KEY_PATH),
        local_public_key_valid = local_public_key_ok,
        remote_public_key_ok = false,
        remote_public_key_status = "not_checked",
        issuer_host_dns_ok = false
    }

    if not parsed then
        details.remote_public_key_status = "invalid issuer url"
        details.ok = false
        return details
    end

    local dns_ok, dns_err = check_dns(parsed.host)
    details.issuer_host_dns_ok = dns_ok
    if not dns_ok then
        details.remote_public_key_status = dns_err or "issuer dns resolution failed"
        details.ok = false
        return details
    end

    if not ok_http then
        details.remote_public_key_status = "resty.http unavailable"
        details.ok = false
        return details
    end

    local url = issuer_origin(parsed) .. "/.well-known/public-key.pem"
    local httpc = resty_http.new()
    httpc:set_timeout(2000)
    local res, err = httpc:request_uri(url, { method = "GET", ssl_verify = true })
    if not res then
        details.remote_public_key_status = err or "issuer request failed"
        details.ok = false
        return details
    end

    if res.status >= 400 then
        details.remote_public_key_status = "http " .. tostring(res.status)
        details.ok = false
        return details
    end

    details.remote_public_key_ok = looks_like_public_key_pem(res.body or "")
    if details.remote_public_key_ok then
        details.remote_public_key_status = "ok"
    else
        details.remote_public_key_status = "invalid public key payload"
    end

    details.ok = details.local_public_key_valid and details.remote_public_key_ok
    return details
end

local lite_mode = is_lite_mode()
local config = ngx.shared and ngx.shared.config
local configured_issuer = trim((config and config:get("issuer")) or os.getenv("ISSUER") or "")
local fmu_runner_enabled = config and config:get("fmu_runner_enabled") == 1
local aas_enabled = config and config:get("aas_enabled") == 1
local local_issuer = build_local_issuer()
local external_issuer = normalize_issuer(configured_issuer) ~= normalize_issuer(local_issuer)

local lite_auth = nil
if lite_mode then
    lite_auth = check_lite_issuer_trust(configured_issuer)
    lite_auth.external_issuer = external_issuer
    lite_auth.local_issuer = local_issuer
    if not external_issuer then
        lite_auth.ok = false
        lite_auth.remote_public_key_status = "issuer points to local gateway; expected external Full issuer in Lite mode"
    end
end

local blockchain = capture("/__health_blockchain")
local guac = capture("/__health_guacamole")
local guac_api = capture("/__health_guac_api")
local ops = capture("/__health_ops")
local fmu_runner = fmu_runner_enabled and capture("/__health_fmu_runner") or { ok = false, status = nil, body = {} }
local aas = aas_enabled and capture("/__health_aas") or { ok = false, status = nil, body = {} }
local mysql_ok, mysql_err = check_mysql()
local guacd_ok, guacd_err = check_guacd()
local guac_schema_ok, guac_schema_err = check_guac_schema()
local guac_api_ok = guac_api.status and guac_api.status < 500

local block_body = blockchain.body or {}
if block_body.billing_configured == nil and block_body.treasury_configured ~= nil then
    block_body.billing_configured = block_body.treasury_configured
end

-- DNS checks
local dns_hosts = { "blockchain-services", "guacamole", "ops-worker", "mysql" }
local dns = {}
for _, h in ipairs(dns_hosts) do
    local ok, err = check_dns(h)
    dns[h] = ok and true or false
end

-- Certificate expiry (days)
local cert_days = cert_days_remaining(FULLCHAIN_PATH)

-- Env/config sanity
local required_env = { "SERVER_NAME", "LAB_MANAGER_TOKEN" }
local env_ok = {}
for _, k in ipairs(required_env) do
    env_ok[k] = (os.getenv(k) ~= nil and os.getenv(k) ~= "")
end

-- Ops worker details (optional)
local ops_body = ops.body or {}

local status_checks = {
    { ok = guac.ok },
    { ok = guac_api_ok },
    { ok = guacd_ok },
    { ok = guac_schema_ok },
    { ok = ops.ok },
    { ok = mysql_ok }
}

if not lite_mode then
    table.insert(status_checks, 1, blockchain)
elseif lite_auth then
    table.insert(status_checks, { ok = lite_auth.ok })
end
if fmu_runner_enabled then
    table.insert(status_checks, { ok = fmu_runner.ok })
end
if aas_enabled then
    table.insert(status_checks, { ok = aas.ok })
end

-- Build structured response
local result = {
    mode = lite_mode and "lite" or "full",
    lite = lite_mode,
    status = overall_status(status_checks),
    services = {
        blockchain = {
            ok = blockchain.ok,
            status = blockchain.status,
            required = not lite_mode,
            details = block_body
        },
        guacamole = {
            ok = guac.ok,
            status = guac.status
        },
        guacamole_api = {
            ok = guac_api_ok,
            status = guac_api.status
        },
        guacd = {
            ok = guacd_ok or false,
            status = guacd_ok and "OK" or guacd_err
        },
        guacamole_schema = {
            ok = guac_schema_ok or false,
            status = guac_schema_ok and "ready" or guac_schema_err
        },
        ops = {
            ok = ops.ok,
            status = ops.status,
            hosts = ops_body.hosts or ops_body.host_count,
            poll_enabled = ops_body.polling_enabled or ops_body.polling
        },
        mysql = {
            ok = mysql_ok or false
        },
        lite_auth = {
            ok = lite_auth and lite_auth.ok or (not lite_mode),
            issuer = lite_auth and lite_auth.issuer or configured_issuer,
            local_issuer = lite_auth and lite_auth.local_issuer or local_issuer,
            external_issuer = lite_auth and lite_auth.external_issuer or false,
            issuer_url_valid = lite_auth and lite_auth.issuer_url_valid or false,
            issuer_host_dns_ok = lite_auth and lite_auth.issuer_host_dns_ok or false,
            local_public_key_present = lite_auth and lite_auth.local_public_key_present or file_exists(PUBLIC_KEY_PATH),
            local_public_key_valid = lite_auth and lite_auth.local_public_key_valid or false,
            remote_public_key_ok = lite_auth and lite_auth.remote_public_key_ok or false,
            remote_public_key_status = lite_auth and lite_auth.remote_public_key_status or "not_applicable"
        },
        fmu_runner = {
            ok = fmu_runner.ok,
            enabled = fmu_runner_enabled,
            status = fmu_runner.status,
            details = fmu_runner.body
        },
        aas = {
            ok = aas.ok,
            enabled = aas_enabled,
            status = aas.status
        }
    },
    infra = {
        dns = dns,
        mysql_up = mysql_ok or false,
        cert = {
            days_remaining = cert_days,
            fullchain_present = file_exists(FULLCHAIN_PATH),
            privkey_present = file_exists(PRIVKEY_PATH)
        },
        static_root_ok = file_exists(STATIC_ROOT_INDEX_PATH),
        env = env_ok
    },
    version = block_body.version
}

ngx.header["Content-Type"] = "application/json"
ngx.say(cjson.encode(result))
