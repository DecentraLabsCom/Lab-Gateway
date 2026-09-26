local runner = require "tests.helpers.runner"

local function read_file(path)
    local file = io.open(path, "r")
    if not file then
        return nil
    end
    local content = file:read("*all")
    file:close()
    return content
end

local function resolve_conf_path()
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../gateway.conf",
        dir .. "/../gateway.conf",
        "openresty/gateway.conf",
        "gateway.conf"
    }

    for _, path in ipairs(candidates) do
        local content = read_file(path)
        if content then
            for _, include_name in ipairs({
                "conf.d/gateway_lab_manager.conf",
                "conf.d/gateway_ops.conf"
            }) do
                local include_candidates = {
                    dir .. "/../../" .. include_name,
                    dir .. "/../" .. include_name,
                    "openresty/" .. include_name,
                    include_name
                }
                for _, include_path in ipairs(include_candidates) do
                    local fragment = read_file(include_path)
                    if fragment then
                        content = content .. "\n" .. fragment
                        break
                    end
                end
            end
            return content
        end
    end

    error("Cannot locate gateway.conf for tests")
end

local function extract_location_block(conf, location)
    local marker = "location " .. location .. " {"
    local start_pos = conf:find(marker, 1, true)
    if not start_pos then
        error("Cannot find location " .. location)
    end

    local body_start = start_pos + #marker
    local depth = 1
    local pos = body_start
    while pos <= #conf do
        local char = conf:sub(pos, pos)
        if char == "{" then
            depth = depth + 1
        elseif char == "}" then
            depth = depth - 1
            if depth == 0 then
                return conf:sub(body_start, pos - 1)
            end
        end
        pos = pos + 1
    end

    error("Unterminated location " .. location)
end

runner.describe("Ops and Lab Manager access configuration", function()
    runner.it("leaves ops health public for readiness checks", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "= /ops/health")

        runner.assert.equals(nil, block:find("access_by_lua_", 1, true))
        runner.assert.truthy(block:find("content_by_lua_file /etc/openresty/lua/public_health.lua", 1, true))
    end)

    runner.it("uses the Lab Manager UI guard and config policy instead of a fixed network ACL", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "/ops/")

        runner.assert.truthy(
            block:find("access_by_lua_file /etc/openresty/lua/lab_manager_access.lua", 1, true),
            "Expected /ops/ to use the Lab Manager UI guard"
        )
        local _, access_directive_count = block:gsub("access_by_lua_", "")
        runner.assert.equals(1, access_directive_count)
        runner.assert.equals(nil, block:find("allow 127.0.0.1", 1, true))
        runner.assert.equals(nil, block:find("deny all", 1, true))
        runner.assert.equals(nil, block:find("$http_x_lab_manager_token", 1, true))
    end)

    runner.it("exposes the WinRM trust lifecycle methods and headers", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "/ops/")

        runner.assert.truthy(
            block:find("Access-Control-Allow-Methods' 'GET, POST, PATCH, PUT, DELETE, OPTIONS'", 1, true),
            "Expected /ops/ to allow the WinRM trust PUT and DELETE lifecycle"
        )
        runner.assert.truthy(
            block:find("X-WinRM-Fingerprint-SHA256", 1, true),
            "Expected /ops/ to allow the WinRM fingerprint confirmation header"
        )
        runner.assert.truthy(
            block:find("X-WinRM-Trust-Ref", 1, true),
            "Expected /ops/ to allow the host trust reference header"
        )
    end)

    runner.it("exposes Lab Manager access policy from environment", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "= /lab-manager/access-policy")

        runner.assert.truthy(block:find("ADMIN_DASHBOARD_LOCAL_ONLY", 1, true))
        runner.assert.truthy(block:find("ADMIN_DASHBOARD_ALLOW_PRIVATE", 1, true))
        runner.assert.truthy(block:find("SECURITY_ALLOW_PRIVATE_NETWORKS", 1, true))
        runner.assert.truthy(block:find("ADMIN_ALLOWED_CIDRS", 1, true))
    end)
end)

return runner
