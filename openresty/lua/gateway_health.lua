local cjson = require "cjson.safe"
local resolver = require "resty.dns.resolver"

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

local function check_mysql()
    local sock = ngx.socket.tcp()
    sock:settimeouts(100, 100, 100)
    local ok, err = sock:connect("mysql", 3306)
    if not ok then
        return false, err
    end
    sock:close()
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
        if mon and months[mon] then
            local local_ts = os.time({
                year = tonumber(year),
                month = months[mon],
                day = tonumber(day),
                hour = tonumber(hour),
                min = tonumber(min),
                sec = tonumber(sec)
            })
            if local_ts then
                local offset = os.difftime(
                    os.time(os.date("*t", local_ts)),
                    os.time(os.date("!*t", local_ts))
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

local blockchain = capture("/__health_blockchain")
local guac = capture("/__health_guacamole")
local guac_api = capture("/__health_guac_api")
local ops = capture("/__health_ops")
local mysql_ok, mysql_err = check_mysql()
local guac_api_ok = guac_api.status and guac_api.status < 500

local block_body = blockchain.body or {}

-- DNS checks
local dns_hosts = { "blockchain-services", "guacamole", "ops-worker", "mysql" }
local dns = {}
for _, h in ipairs(dns_hosts) do
    local ok, err = check_dns(h)
    dns[h] = ok and true or false
end

-- Certificate expiry (days)
local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close() return true end
    return false
end
local cert_days = cert_days_remaining("/etc/ssl/private/fullchain.pem")

-- Env/config sanity
local required_env = { "SERVER_NAME", "OPS_SECRET" }
local env_ok = {}
for _, k in ipairs(required_env) do
    env_ok[k] = (os.getenv(k) ~= nil and os.getenv(k) ~= "")
end

-- Ops worker details (optional)
local ops_body = ops.body or {}

-- Build structured response
local result = {
    status = overall_status({
        blockchain,
        { ok = guac.ok },
        { ok = guac_api_ok },
        { ok = ops.ok },
        { ok = mysql_ok }
    }),
    services = {
        blockchain = {
            ok = blockchain.ok,
            status = blockchain.status,
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
        ops = {
            ok = ops.ok,
            status = ops.status,
            hosts = ops_body.hosts or ops_body.host_count,
            poll_enabled = ops_body.polling_enabled or ops_body.polling
        },
        mysql = {
            ok = mysql_ok or false
        }
    },
    infra = {
        dns = dns,
        mysql_up = mysql_ok or false,
        cert = {
            days_remaining = cert_days,
            fullchain_present = file_exists("/etc/ssl/private/fullchain.pem"),
            privkey_present = file_exists("/etc/ssl/private/privkey.pem")
        },
        static_root_ok = file_exists("/var/www/html/index.html"),
        env = env_ok
    },
    version = block_body.version
}

ngx.header["Content-Type"] = "application/json"
ngx.say(cjson.encode(result))
