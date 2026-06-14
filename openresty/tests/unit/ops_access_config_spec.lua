local runner = require "tests.helpers.runner"

local function resolve_conf_path()
    local source = debug.getinfo(1, "S").source
    if source:sub(1, 1) == "@" then
        source = source:sub(2)
    end
    source = source:gsub("\\", "/")
    local dir = source:match("^(.*)/[^/]+$") or "."

    local candidates = {
        dir .. "/../../lab_access.conf",
        dir .. "/../lab_access.conf",
        "openresty/lab_access.conf",
        "lab_access.conf"
    }

    for _, path in ipairs(candidates) do
        local file = io.open(path, "r")
        if file then
            local content = file:read("*all")
            file:close()
            return content
        end
    end

    error("Cannot locate lab_access.conf for tests")
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

runner.describe("Ops access configuration", function()
    runner.it("leaves ops health public for readiness checks", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "= /ops/health")

        runner.assert.equals(nil, block:find("access_by_lua_", 1, true))
        runner.assert.truthy(block:find("proxy_pass $ops_health_upstream", 1, true))
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
