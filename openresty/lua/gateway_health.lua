local cjson = require "cjson.safe"
local resolver = require "resty.dns.resolver"
local ok_http, resty_http = pcall(require, "resty.http")
local demo_readiness = require "demo_readiness"
local health_values = require "gateway_health_values"

local PUBLIC_KEY_PATH = "/etc/ssl/private/public_key.pem"
local FULLCHAIN_PATH = "/etc/ssl/private/fullchain.pem"
local PRIVKEY_PATH = "/etc/ssl/private/privkey.pem"
local STATIC_ROOT_INDEX_PATH = "/var/www/html/index.html"

local trim = health_values.trim
local normalize_issuer = health_values.normalize_issuer

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

local looks_like_public_key_pem = health_values.looks_like_public_key_pem
local canonical_public_key = health_values.canonical_public_key
local parse_issuer_url = health_values.parse_issuer_url
local issuer_origin = health_values.issuer_origin

local function is_lite_mode()
    local config = ngx.shared and ngx.shared.config
    local value = config and config:get("lite_mode")
    return health_values.lite_mode_enabled(value)
end

local function build_local_issuer()
    local config = ngx.shared and ngx.shared.config
    local server_name = (config and config:get("server_name")) or os.getenv("SERVER_NAME") or "localhost"
    local https_port = (config and config:get("https_port")) or os.getenv("HTTPS_PORT") or "443"
    return health_values.build_local_issuer(server_name, https_port)
end

local function capture(path)
    local res = ngx.location.capture(path)
    if not res then
        return health_values.capture_result(nil)
    end
    local body = res.body or ""
    local parsed = cjson.decode(body) or {}
    return health_values.capture_result(res, parsed, body)
end

local blockchain_ready = health_values.blockchain_ready

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

local function cert_days_remaining(path)
    local f = io.popen("openssl x509 -enddate -noout -in " .. path .. " 2>/dev/null")
    if not f then return nil end
    local out = f:read("*a") or ""
    f:close()
    local notAfter = out:match("notAfter=([^\r\n]+)")
    if not notAfter then return nil end
    return health_values.certificate_days_remaining(notAfter, ngx.time(), ngx.parse_http_time)
end

local overall_status = health_values.overall_status

local function check_lite_issuer_trust(issuer)
    -- init.lua stores the exact mode-selected key in shared memory. Use that
    -- active value for trust checks so a stale certs/ key cannot mask a
    -- failed remote-key sync (the file fallback keeps unit tests and early
    -- startup diagnostics useful before init.lua has populated the cache).
    local config = ngx.shared and ngx.shared.config
    local cache = ngx.shared and ngx.shared.cache
    local local_public_key = cache and cache:get("public_key") or nil
    local active_public_key_source = config and config:get("jwt_public_key_path") or nil
    if not local_public_key then
        active_public_key_source = active_public_key_source or PUBLIC_KEY_PATH
        local_public_key = read_file(active_public_key_source)
    end
    local local_public_key_ok = looks_like_public_key_pem(local_public_key)
    local parsed = parse_issuer_url(issuer)
    local details = {
        issuer = issuer,
        issuer_url_valid = parsed ~= nil,
        active_public_key_source = active_public_key_source or "shared-cache",
        local_public_key_present = local_public_key ~= nil and local_public_key ~= "",
        local_public_key_valid = local_public_key_ok,
        remote_public_key_ok = false,
        public_key_matches = false,
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

    local remote_public_key = res.body or ""
    details.remote_public_key_ok = looks_like_public_key_pem(remote_public_key)
    details.public_key_matches = details.remote_public_key_ok
        and canonical_public_key(local_public_key) == canonical_public_key(remote_public_key)
    if details.remote_public_key_ok and details.public_key_matches then
        details.remote_public_key_status = "ok"
    elseif details.remote_public_key_ok then
        details.remote_public_key_status = "public key mismatch"
    else
        details.remote_public_key_status = "invalid public key payload"
    end

    details.ok = details.local_public_key_valid
        and details.remote_public_key_ok
        and details.public_key_matches
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
local ops_body = ops.body or {}
local mysql_ok, mysql_err
if ops_body.db ~= nil then
    mysql_ok = ops_body.db == true
    mysql_err = mysql_ok and nil or "ops-worker reports MySQL unavailable"
else
    mysql_ok, mysql_err = check_mysql()
end
local guacd_ok, guacd_err = check_guacd()
local guac_api_ok = guac_api.status and guac_api.status < 500
local guac_reachable = guac.reachable == true
local guac_api_reachable = guac_api.reachable == true
local ops_reachable = ops.reachable == true

local fmu_runner_body = fmu_runner.body or {}
local fmu_runner_payload_status = tostring(fmu_runner_body.status or ""):upper()
local fmu_runner_ok = fmu_runner.ok and fmu_runner_payload_status == "UP"
local fmu_runner_status = fmu_runner.status

local block_body = blockchain.body or {}
if block_body.billing_configured == nil and block_body.treasury_configured ~= nil then
    block_body.billing_configured = block_body.treasury_configured
end
local blockchain_reachable = blockchain.reachable == true
local blockchain_ok = blockchain_ready(blockchain)

-- DNS checks
local dns_hosts = { "blockchain-services", "guacamole", "ops-worker", "mysql" }
local dns = {}
for _, h in ipairs(dns_hosts) do
    if h == "mysql" and ops_body.db ~= nil then
        dns[h] = ops_body.db == true
    else
        local ok, err = check_dns(h)
        dns[h] = ok and true or false
    end
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
local guacamole_schema_ok = ops_body.guacamole_schema == true

local status_checks = health_values.build_status_checks({
    lite_mode = lite_mode,
    lite_auth = lite_auth,
    blockchain_ok = blockchain_ok,
    blockchain_reachable = blockchain_reachable,
    guac_ok = guac.ok,
    guac_reachable = guac_reachable,
    guac_api_ok = guac_api_ok,
    guac_api_reachable = guac_api_reachable,
    guacd_ok = guacd_ok,
    ops_ok = ops.ok,
    ops_reachable = ops_reachable,
    guacamole_schema_ok = guacamole_schema_ok,
    mysql_ok = mysql_ok,
    fmu_runner_enabled = fmu_runner_enabled,
    fmu_runner_ok = fmu_runner_ok,
    fmu_runner_reachable = fmu_runner.reachable == true,
    aas_enabled = aas_enabled,
    aas_ok = aas.ok,
    aas_reachable = aas.reachable == true
})

local gateway_status = overall_status(status_checks)
local demo = demo_readiness.evaluate({
    config = config,
    core_ready = gateway_status == "UP",
    ops = ops,
    now = ngx.time(),
    http_module = ok_http and resty_http or nil
})

-- Build structured response
local result = health_values.build_result({
    lite_mode = lite_mode,
    gateway_status = gateway_status,
    demo = demo,
    blockchain = blockchain,
    blockchain_ok = blockchain_ok,
    blockchain_reachable = blockchain_reachable,
    block_body = block_body,
    guac = guac,
    guac_api = guac_api,
    guac_api_ok = guac_api_ok,
    guacd_ok = guacd_ok,
    guacd_err = guacd_err,
    ops = ops,
    ops_body = ops_body,
    guacamole_schema_ok = guacamole_schema_ok,
    mysql_ok = mysql_ok,
    lite_auth = lite_auth,
    configured_issuer = configured_issuer,
    local_issuer = local_issuer,
    public_key_file_present = file_exists(PUBLIC_KEY_PATH),
    fmu_runner_ok = fmu_runner_ok,
    fmu_runner_enabled = fmu_runner_enabled,
    fmu_runner_status = fmu_runner_status,
    fmu_runner_body = fmu_runner_body,
    aas = aas,
    aas_enabled = aas_enabled,
    dns = dns,
    cert_days = cert_days,
    fullchain_present = file_exists(FULLCHAIN_PATH),
    privkey_present = file_exists(PRIVKEY_PATH),
    static_root_ok = file_exists(STATIC_ROOT_INDEX_PATH),
    env_ok = env_ok
})

ngx.header["Content-Type"] = "application/json"
ngx.status = result.status == "UP" and 200 or 503
ngx.say(cjson.encode(result))
