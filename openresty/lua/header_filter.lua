-- ============================================================================
-- header_filter.lua - Header Filter Phase (header_filter_by_lua)
-- ============================================================================
-- Delegates to dedicated handler module so the logic can be unit tested while
-- keeping OpenResty's entry point unchanged.
-- ============================================================================
local handler = require "modules.header_filter_handler"

handler.run(ngx)

