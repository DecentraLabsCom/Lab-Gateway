package.path = table.concat({
    "./openresty/lua/?.lua",
    "./openresty/lua/?/init.lua",
    "./openresty/?.lua",
    "./openresty/?/init.lua"
}, ";") .. ";" .. package.path

local runner = require "tests.helpers.runner"

local specs = {
    "tests.unit.access_handler_spec",
    "tests.unit.access_handler_extended_spec",
    "tests.unit.header_filter_handler_spec",
    "tests.unit.header_filter_handler_extended_spec",
    "tests.unit.session_guard_spec",
    "tests.unit.session_guard_extended_spec",
    "tests.unit.log_handler_spec",
    "tests.unit.log_handler_extended_spec",
    "tests.unit.body_filter_handler_spec",
    "tests.unit.body_filter_handler_extended_spec",
    "tests.unit.internal_access_spec"
}

for _, spec in ipairs(specs) do
    require(spec)
end

local ok = runner.run()
if not ok then
    os.exit(1)
end
