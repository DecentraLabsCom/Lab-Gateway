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

local ACCESS_CODE_EXCHANGE_PATH = resolve_lua_path("access_code_exchange.lua")

local function with_environment(env, fn)
    local previous_getenv = os.getenv
    os.getenv = function(name)
        return env[name]
    end
    local ok, result = xpcall(fn, debug.traceback)
    os.getenv = previous_getenv
    if not ok then
        error(result, 0)
    end
    return result
end

local function with_modules(stubs, fn)
    local previous_loaded = {}
    local previous_preload = {}
    for name, module in pairs(stubs) do
        previous_loaded[name] = package.loaded[name]
        previous_preload[name] = package.preload[name]
        package.loaded[name] = nil
        package.preload[name] = function()
            return module
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

local function run_exchange(opts)
    opts = opts or {}
    local events = {}
    local responses = opts.responses or {
        { status = 200, body = "prepared" },
        { status = 204 }
    }
    local claims = opts.claims or {
        jti = "jti-1234567890123456",
        sub = "dlabs-res-user",
        exp = 1000,
        iss = "https://gateway.example/auth",
        aud = "https://gateway.example/guacamole",
        resourceType = "lab",
        reservationKey = "0xabc"
    }

    local cache = ngx_factory.new_shared_dict({ public_key = "public-key" })
    local original_set = cache.set
    function cache:set(key, value, ttl)
        events[#events + 1] = { kind = "cache", key = key, value = value, ttl = ttl }
        if opts.fail_cache_key == key then
            return nil, "no memory"
        end
        return original_set(self, key, value, ttl)
    end

    local config = ngx_factory.new_shared_dict({
        server_name = "gateway.example",
        gateway_id = "gateway.example",
        https_port = "443",
        issuer = "https://gateway.example/auth"
    })
    local ngx = ngx_factory.new({
        method = "POST",
        now = 100,
        cache_dict = cache,
        config_dict = config,
        var = {
            host = "gateway.example",
            http_host = "gateway.example"
        }
    })
    function ngx.req.get_post_args()
        return { access_code = "opaque-code" }
    end

    local http_stub = {
        new = function()
            local client = {}
            function client:set_timeout() end
            function client:request_uri(url, request)
                events[#events + 1] = {
                    kind = "http",
                    url = url,
                    request = request
                }
                return table.remove(responses, 1)
            end
            return client
        end
    }
    local cjson_stub = {
        encode = function()
            return "{}"
        end,
        decode = function()
            return {
                token = "signed-jwt",
                labURL = "https://gateway.example/guacamole/",
                redemptionHandle = "handle-1"
            }
        end
    }
    local jwt_stub = {
        load_jwt = function()
            return { valid = true }
        end,
        verify_jwt_obj = function()
            return { verified = true, payload = claims }
        end
    }
    local fmu_store_stub = {
        default = {
            save = function()
                return true
            end,
            remove = function() end
        }
    }

    with_environment({
        AUTH_ACCESS_CODE_REDEEM_URL = "https://gateway.example/auth/access-code/redeem",
        AUTH_ACCESS_CODE_REDEEMER_TOKEN = "redeemer"
    }, function()
        with_modules({
            ["cjson.safe"] = cjson_stub,
            ["resty.http"] = http_stub,
            ["resty.jwt"] = jwt_stub,
            ["modules.fmu_access_store"] = fmu_store_stub
        }, function()
            _G.ngx = ngx
            local ok, err = xpcall(function()
                dofile(ACCESS_CODE_EXCHANGE_PATH)
            end, debug.traceback)
            _G.ngx = nil
            if not ok then
                error(err, 0)
            end
        end)
    end)

    return ngx, cache, events
end

local function assert_no_guacamole_mappings(cache)
    runner.assert.equals(nil, cache:get("username:jti-1234567890123456"))
    runner.assert.equals(nil, cache:get("exp:dlabs-res-user"))
    runner.assert.equals(nil, cache:get("guac_enforcement_exp:dlabs-res-user"))
    runner.assert.equals(nil, cache:get("reservation:jti-1234567890123456"))
end

runner.describe("Access-code Guacamole exchange", function()
    runner.it("stores every local mapping before committing the redemption", function()
        local ngx, cache, events = run_exchange()

        runner.assert.equals(303, ngx.status)
        runner.assert.equals("dlabs-res-user", cache:get("username:jti-1234567890123456"))
        runner.assert.equals(1000, cache:get("exp:dlabs-res-user"))
        runner.assert.equals(1000, cache:get("guac_enforcement_exp:dlabs-res-user"))
        runner.assert.equals("0xabc", cache:get("reservation:jti-1234567890123456"))
        runner.assert.equals("http", events[1].kind)
        runner.assert.equals("cache", events[2].kind)
        runner.assert.equals("cache", events[3].kind)
        runner.assert.equals("cache", events[4].kind)
        runner.assert.equals("cache", events[5].kind)
        runner.assert.equals("http", events[6].kind)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem/commit", events[6].url)
    end)

    runner.it("releases the handle without committing when a mapping cannot be stored", function()
        local ngx, cache, events = run_exchange({
            fail_cache_key = "reservation:jti-1234567890123456",
            responses = {
                { status = 200, body = "prepared" },
                { status = 204 }
            }
        })

        runner.assert.equals(503, ngx.status)
        assert_no_guacamole_mappings(cache)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem", events[1].url)
        runner.assert.equals("cache", events[5].kind)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem/release", events[6].url)
    end)

    runner.it("rejects a lab credential without reservationKey before consuming it", function()
        local claims = {
            jti = "jti-1234567890123456",
            sub = "dlabs-res-user",
            exp = 1000,
            iss = "https://gateway.example/auth",
            aud = "https://gateway.example/guacamole",
            resourceType = "lab"
        }
        local ngx, cache, events = run_exchange({ claims = claims })

        runner.assert.equals(401, ngx.status)
        assert_no_guacamole_mappings(cache)
        runner.assert.equals(2, #events)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem", events[1].url)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem/release", events[2].url)
    end)

    runner.it("rolls back local mappings when the commit fails", function()
        local ngx, cache, events = run_exchange({
            responses = {
                { status = 200, body = "prepared" },
                { status = 503 },
                { status = 204 }
            }
        })

        runner.assert.equals(503, ngx.status)
        assert_no_guacamole_mappings(cache)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem/commit", events[6].url)
        runner.assert.equals("https://gateway.example/auth/access-code/redeem/release", events[7].url)
    end)
end)

return runner
