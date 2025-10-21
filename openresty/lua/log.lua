-- ============================================================================
-- log.lua - Log Phase (log_by_lua)
-- ============================================================================
-- Runs AFTER the response has been sent to the client.
-- Purpose: Detect when a Guacamole WebSocket tunnel closes and revoke the
-- web session for non-admin users who authenticated manually (not via JWT).
-- This ensures users are logged out when they disconnect from RDP/VNC/SSH.
-- ============================================================================

-- Only process WebSocket tunnel requests
local uri = ngx.var.uri
if not uri:match("/guacamole/websocket%-tunnel") then
	return
end

-- Only process if the connection is being closed (not still active)
local status = ngx.var.status
-- Status 101 = Switching Protocols (WebSocket established, still active)
-- Status 400/403/404/5xx = Error closing
-- Status 200/204 = Normal closure
if status == "101" then
	return  -- Connection still active, don't process
end

-- Check if auto-logout feature is enabled
local config = ngx.shared.config
local auto_logout_enabled = config:get("auto_logout_on_disconnect")
if not auto_logout_enabled then
	ngx.log(ngx.DEBUG, "Log - Auto-logout on disconnect is disabled")
	return
end

-- Try to get username from Authorization header (JWT users)
local username = ngx.var.http_authorization

-- If no Authorization header, try to extract from WebSocket token (manual login users)
if not username or username == "" then
	-- WebSocket tunnels use query string like: ?token=GUAC_TOKEN
	local args = ngx.var.args
	if args then
		local token = args:match("token=([^&]+)")
		if token then
			-- Fast O(1) lookup using reverse mapping
			local dict = ngx.shared.cache
			username = dict:get("guac_token:" .. token)
			if username then
				ngx.log(ngx.DEBUG, "Log - Found username from token: " .. username)
			end
		end
	end
	
	-- Still no username found
	if not username or username == "" then
		ngx.log(ngx.DEBUG, "Log - No username found for tunnel closure")
		return
	end
end

username = string.lower(username)

-- Skip admin user
local config = ngx.shared.config
local admin_user = config:get("admin_user")
if username == string.lower(admin_user) then
	ngx.log(ngx.DEBUG, "Log - Skipping tunnel closure for admin user: " .. username)
	return
end

-- Check if this is a JWT-authenticated user (has exp:username in dict)
local dict = ngx.shared.cache
local exp = dict:get("exp:" .. username)
if exp then
	-- This is a JWT user, managed by worker - don't revoke here
	ngx.log(ngx.DEBUG, "Log - Skipping JWT-authenticated user: " .. username)
	return
end

-- This is a manually logged-in user - mark for session revocation
-- Store timestamp of tunnel closure
local now = ngx.time()
dict:set("tunnel_closed:" .. username, now, 300)  -- TTL 5 minutes

-- Set flag to notify worker there are pending closures
dict:set("has_pending_closures", "1", 300)

-- Add username to pending set for O(1) iteration (format: "pending_user:username")
dict:set("pending_user:" .. username, "1", 300)

ngx.log(ngx.INFO, "Log - Tunnel closed for user: " .. username .. " (status: " .. status .. "), marked for session revocation")
