-- ============================================================================
-- access.lua - Access Phase (access_by_lua)
-- ============================================================================
-- Runs BEFORE the request is proxied to Guacamole backend.
-- Purpose: Validate the JTI cookie from the client. If valid, set the
-- Authorization header with the username to be sent to Guacamole. If invalid
-- or missing, proceed without authentication (Guacamole will handle it).
-- ============================================================================

local handler = require "modules.access_handler"

handler.run(ngx)
