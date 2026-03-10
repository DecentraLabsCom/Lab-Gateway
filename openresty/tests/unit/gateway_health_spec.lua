local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"

local function resolve_lua_path(name)
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lua/" .. name,
        dir .. "/../lua/" .. name,
        "openresty/lua/" .. name,
        "lua/" .. name
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            file:close()
            return path
        end
    end

    error("Cannot locate " .. name .. " for tests")
end

local GATEWAY_HEALTH_LUA_PATH = resolve_lua_path("gateway_health.lua")

local function with_module_stubs(stubs, fn)
    local previous_loaded = {}
    local previous_preload = {}

    for name, module in pairs(stubs) do
        local provided = module
        previous_loaded[name] = package.loaded[name]
        previous_preload[name] = package.preload[name]
        package.loaded[name] = nil
        package.preload[name] = function()
            return provided
        end
    end

    local ok, result = xpcall(fn, debug.traceback)

    for name in pairs(stubs) do
        package.loaded[name] = previous_loaded[name]
        package.preload[name] = previous_preload[name]
    end

    if not ok then
        error(result, 0)
    end

    return result
end

local function with_gateway_runtime(opts, fn)
    local previous_getenv = os.getenv
    local previous_open = io.open
    local previous_popen = io.popen
    local previous_ngx = _G.ngx
    local env = opts.env or {}
    local files = opts.files or {}

    ---@diagnostic disable-next-line: duplicate-set-field
    os.getenv = function(name)
        return env[name]
    end

    io.open = function(path, mode)
        local content = files[path]
        if content == nil then
            return nil
        end

        return {
            read = function(_, pattern)
                return content
            end,
            close = function() end
        }
    end

    io.popen = function(command)
        local output = opts.openssl_output
        if output == nil then
            return nil
        end

        return {
            read = function(_, pattern)
                return output
            end,
            close = function() end
        }
    end

    _G.ngx = opts.ngx

    local ok, result = xpcall(fn, debug.traceback)

    _G.ngx = previous_ngx
    os.getenv = previous_getenv
    io.open = previous_open
    io.popen = previous_popen

    if not ok then
        error(result, 0)
    end

    return result
end

local function build_dns_stub(map)
    local resolver = {}

    function resolver:new(opts)
        return {
            query = function(_, host)
                local entry = map[host]
                if entry == false then
                    return nil, "dns failed"
                end
                return {
                    { address = entry or "127.0.0.1" }
                }
            end
        }
    end

    return resolver
end

local function build_http_stub(map)
    return {
        new = function()
            return {
                set_timeout = function(_, timeout) end,
                request_uri = function(_, url, options)
                    local entry = map[url]
                    if not entry then
                        return nil, "unexpected request"
                    end
                    if entry.ok == false then
                        return nil, entry.err or "request failed"
                    end
                    return {
                        status = entry.status or 200,
                        body = entry.body
                    }
                end
            }
        end
    }
end

local function build_mysql_stub(opts)
    return {
        new = function()
            return {
                set_timeout = function(_, timeout) end,
                connect = function(_, params)
                    if opts.connect == false then
                        return nil, opts.connect_err or "mysql connect failed"
                    end
                    return true
                end,
                query = function(_, query)
                    if opts.query == false then
                        return nil, opts.query_err or "mysql query failed"
                    end
                    return { { value = 1 } }
                end,
                set_keepalive = function(_, max_idle_timeout, pool_size) end
            }
        end
    }
end

local function run_gateway_health(opts)
    local ngx = ngx_factory.new({
        config = opts.config or {},
        now = opts.now or 0
    })

    ngx.header = {}
    ngx.say = function(message)
        ngx._body = message
    end
    ngx.location = {
        capture = function(path)
            return (opts.captures or {})[path]
        end
    }

    local tcp_results = opts.tcp or {}
    ngx.socket = {
        tcp = function()
            return {
                settimeouts = function(_, connect_timeout, send_timeout, read_timeout) end,
                connect = function(_, host, port)
                    local entry = tcp_results[host .. ":" .. tostring(port)]
                    if entry == false then
                        return nil, "connection refused"
                    end
                    return true
                end,
                close = function() end
            }
        end
    }

    ngx.parse_http_time = function(value)
        return opts.cert_expiry
    end

    local cjson_stub = {
        encode = function(value)
            return value
        end,
        decode = function(value)
            if type(value) == "table" then
                return value
            end
            return nil
        end
    }

    with_module_stubs({
        ["cjson.safe"] = cjson_stub,
        ["resty.dns.resolver"] = build_dns_stub(opts.dns or {}),
        ["resty.http"] = build_http_stub(opts.http or {}),
        ["resty.mysql"] = build_mysql_stub(opts.mysql or {})
    }, function()
        with_gateway_runtime({
            env = opts.env,
            files = opts.files,
            openssl_output = opts.openssl_output,
            ngx = ngx
        }, function()
            dofile(GATEWAY_HEALTH_LUA_PATH)
        end)
    end)

    return ngx
end

local function healthy_gateway_health_opts()
    return {
        config = {
            lite_mode = 0,
            issuer = "https://gateway.example/auth",
            server_name = "gateway.example",
            https_port = "443"
        },
        env = {
            SERVER_NAME = "gateway.example",
            LAB_MANAGER_TOKEN = "lab-token",
            MYSQL_USER = "guac",
            MYSQL_PASSWORD = "mysql-secret",
            MYSQL_DATABASE = "guacamole_db"
        },
        files = {
            ["/etc/ssl/private/public_key.pem"] = "-----BEGIN PUBLIC KEY-----\nlocal\n-----END PUBLIC KEY-----",
            ["/etc/ssl/private/fullchain.pem"] = "certificate",
            ["/etc/ssl/private/privkey.pem"] = "private-key",
            ["/var/www/html/index.html"] = "<html></html>"
        },
        captures = {
            ["/__health_blockchain"] = { status = 200, body = { version = "1.2.3" } },
            ["/__health_guacamole"] = { status = 200, body = {} },
            ["/__health_guac_api"] = { status = 200, body = {} },
            ["/__health_ops"] = { status = 200, body = { hosts = 3, polling_enabled = true } }
        },
        dns = {
            ["blockchain-services"] = "10.0.0.2",
            guacamole = "10.0.0.3",
            ["ops-worker"] = "10.0.0.4",
            mysql = "10.0.0.5",
            ["gateway.example"] = "10.0.0.10"
        },
        http = {
            ["https://gateway.example/.well-known/public-key.pem"] = {
                status = 200,
                body = "-----BEGIN PUBLIC KEY-----\nremote\n-----END PUBLIC KEY-----"
            }
        },
        mysql = {
            connect = true,
            query = true
        },
        openssl_output = "notAfter=Jan 12 00:00:00 1970 GMT\n",
        cert_expiry = 86400 * 42,
        now = 0
    }
end

runner.describe("OpenResty gateway_health.lua", function()
    runner.it("reports UP when the full gateway stack is healthy", function()
        local ngx = run_gateway_health(healthy_gateway_health_opts())

        local result = ngx._body
        runner.assert.equals("application/json", ngx.header["Content-Type"])
        runner.assert.equals("full", result.mode)
        runner.assert.equals("UP", result.status)
        runner.assert.equals(true, result.services.blockchain.ok)
        runner.assert.equals(true, result.services.guacamole.ok)
        runner.assert.equals(true, result.services.mysql.ok)
        runner.assert.equals(42, result.infra.cert.days_remaining)
        runner.assert.equals(true, result.infra.static_root_ok)
        runner.assert.equals("1.2.3", result.version)
    end)

    runner.it("marks lite auth as degraded when ISSUER points back to the local gateway", function()
        local opts = healthy_gateway_health_opts()
        opts.config.lite_mode = 1
        opts.captures["/__health_ops"] = { status = 200, body = { hosts = 1, polling_enabled = true } }
        opts.cert_expiry = 86400 * 14

        local ngx = run_gateway_health(opts)

        local result = ngx._body
        runner.assert.equals("lite", result.mode)
        runner.assert.equals("PARTIAL", result.status)
        runner.assert.equals(false, result.services.lite_auth.ok)
        runner.assert.equals(false, result.services.lite_auth.external_issuer)
        runner.assert.truthy(result.services.lite_auth.remote_public_key_status:find("expected external Full issuer", 1, true) ~= nil)
    end)

    runner.it("reports DOWN when upstreams and infrastructure checks fail", function()
        local opts = healthy_gateway_health_opts()
        opts.captures = {
            ["/__health_guacamole"] = { status = 503, body = {} },
            ["/__health_guac_api"] = { status = 504, body = {} }
        }
        opts.dns = {
            ["blockchain-services"] = false,
            guacamole = false,
            ["ops-worker"] = false,
            mysql = false
        }
        opts.tcp = {
            ["mysql:3306"] = false,
            ["guacd:4822"] = false
        }
        opts.mysql = {
            connect = false,
            connect_err = "mysql connect failed"
        }

        local ngx = run_gateway_health(opts)

        local result = ngx._body
        runner.assert.equals("DOWN", result.status)
        runner.assert.equals(false, result.services.blockchain.ok)
        runner.assert.equals(false, result.services.guacamole.ok)
        runner.assert.equals(false, result.services.guacamole_api.ok)
        runner.assert.equals("connection refused", result.services.guacd.status)
        runner.assert.equals("mysql connect failed", result.services.guacamole_schema.status)
        runner.assert.equals(false, result.infra.dns["blockchain-services"])
        runner.assert.equals(false, result.infra.mysql_up)
    end)

    runner.it("marks lite auth as degraded when the issuer URL is invalid", function()
        local opts = healthy_gateway_health_opts()
        opts.config.lite_mode = 1
        opts.config.issuer = "not-a-valid-url"

        local ngx = run_gateway_health(opts)

        local result = ngx._body
        runner.assert.equals("lite", result.mode)
        runner.assert.equals("PARTIAL", result.status)
        runner.assert.equals(false, result.services.lite_auth.ok)
        runner.assert.equals(false, result.services.lite_auth.issuer_url_valid)
        runner.assert.equals("invalid issuer url", result.services.lite_auth.remote_public_key_status)
    end)

    runner.it("marks lite auth as degraded when the remote public key payload is malformed", function()
        local opts = healthy_gateway_health_opts()
        opts.config.lite_mode = 1
        opts.config.issuer = "https://issuer.example/auth"
        opts.dns["issuer.example"] = "10.0.0.11"
        opts.http = {
            ["https://issuer.example/.well-known/public-key.pem"] = {
                status = 200,
                body = "not a pem"
            }
        }

        local ngx = run_gateway_health(opts)

        local result = ngx._body
        runner.assert.equals("lite", result.mode)
        runner.assert.equals("PARTIAL", result.status)
        runner.assert.equals(false, result.services.lite_auth.ok)
        runner.assert.equals(true, result.services.lite_auth.issuer_url_valid)
        runner.assert.equals(true, result.services.lite_auth.issuer_host_dns_ok)
        runner.assert.equals(false, result.services.lite_auth.remote_public_key_ok)
        runner.assert.equals("invalid public key payload", result.services.lite_auth.remote_public_key_status)
    end)

    runner.it("marks guacamole schema as degraded when mysql credentials are missing", function()
        local opts = healthy_gateway_health_opts()
        opts.env.MYSQL_PASSWORD = ""

        local ngx = run_gateway_health(opts)

        local result = ngx._body
        runner.assert.equals("PARTIAL", result.status)
        runner.assert.equals(false, result.services.guacamole_schema.ok)
        runner.assert.equals("mysql credentials missing", result.services.guacamole_schema.status)
        runner.assert.equals(true, result.services.mysql.ok)
    end)
end)

return runner
