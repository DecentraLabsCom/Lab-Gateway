-- ============================================================================
-- log.lua - Log Phase (log_by_lua)
-- ============================================================================
-- Runs AFTER the response has been sent to the client.
-- Purpose: Detect when a Guacamole WebSocket tunnel closes and revoke the
-- web session for non-admin users who authenticated manually (not via JWT).
-- This ensures users are logged out when they disconnect from RDP/VNC/SSH.
-- ============================================================================

local handler = require "modules.log_handler"

handler.run(ngx)
