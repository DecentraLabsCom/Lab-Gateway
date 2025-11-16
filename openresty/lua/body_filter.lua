-- ============================================================================
-- body_filter.lua - Body Filter Phase (body_filter_by_lua)
-- ============================================================================
-- Runs when processing response BODY chunks from Guacamole (after headers).
-- Purpose: Capture Guacamole's JSON authentication response containing
-- authToken and username. Stores the authToken in shared dict so that
-- init_worker can later revoke it when the JWT session expires.
-- ============================================================================

local handler = require "modules.body_filter_handler"

handler.run(ngx, ngx.arg[1], ngx.arg[2])
