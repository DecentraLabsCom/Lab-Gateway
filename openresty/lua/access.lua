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

-- The public Guacamole token endpoint also accepts manual username/password
-- logins.  Apply its credential-attempt guard after the normal session-cookie
-- handling, while leaving the private /__guacamole_tokens subrequest
-- untouched (that location is internal-only and never reaches this file).
if ngx.var.uri == "/guacamole/api/tokens" then
    local login_guard = require "modules.guacamole_login_guard"
    login_guard.run(ngx)
end
