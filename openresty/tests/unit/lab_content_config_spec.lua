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

runner.describe("Lab content OpenResty configuration", function()
    runner.it("serves lab content from a read-only static alias", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "/lab-content/")

        runner.assert.truthy(block:find("alias /var/www/lab-content/;", 1, true))
        runner.assert.truthy(block:find("try_files $uri =404;", 1, true))
        runner.assert.truthy(block:find("disable_symlinks on from=/var/www/lab-content;", 1, true))
        runner.assert.equals(nil, block:find("proxy_pass", 1, true))
    end)

    runner.it("keeps lab content public but read-only", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "/lab-content/")

        runner.assert.truthy(block:find("GET|HEAD|OPTIONS", 1, true))
        runner.assert.truthy(block:find("return 405;", 1, true))
        runner.assert.truthy(block:find("Access-Control-Allow-Origin \"*\"", 1, true))
        runner.assert.truthy(block:find("Access-Control-Allow-Methods \"GET, HEAD, OPTIONS\"", 1, true))
        runner.assert.truthy(block:find("Access-Control-Allow-Headers \"Content-Type\"", 1, true))
        runner.assert.truthy(block:find("Cache-Control \"public, max-age=3600\"", 1, true))
        runner.assert.truthy(block:find("X-Content-Type-Options \"nosniff\"", 1, true))
    end)

    runner.it("keeps lab admin protected and allows long blockchain transactions", function()
        local conf = resolve_conf_path()
        local block = extract_location_block(conf, "/lab-admin/")

        runner.assert.truthy(block:find("access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua", 1, true))
        runner.assert.truthy(block:find("proxy_read_timeout 180s;", 1, true))
        runner.assert.truthy(block:find("proxy_send_timeout 180s;", 1, true))
        runner.assert.truthy(block:find('proxy_set_header Origin "";', 1, true))
        runner.assert.truthy(block:find('set $backend_lab_admin "";', 1, true))
        runner.assert.truthy(block:find("proxy_ssl_server_name on;", 1, true))
        runner.assert.truthy(block:find("proxy_pass $backend_lab_admin;", 1, true))
    end)

    runner.it("overwrites forwarded client headers before proxying", function()
        local conf = resolve_conf_path()

        runner.assert.equals(nil, conf:find("proxy_add_x_forwarded_for", 1, true))
        runner.assert.truthy(conf:find("proxy_set_header X-Forwarded-For $remote_addr;", 1, true))
    end)
end)

return runner
