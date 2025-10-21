-- ============================================================================
-- init_worker.lua - Worker Initialization Phase (init_worker_by_lua)
-- ============================================================================
-- Runs once per worker process when it starts.
-- Purpose: Set up a periodic timer (every 30 seconds) that checks for expired
-- JWT sessions. For expired sessions, it terminates active Guacamole connections
-- and revokes Guacamole session tokens via the Guacamole REST API.
-- ============================================================================

-- Load modules once per worker (cached automatically by OpenResty)
local http = require "resty.http"
local cjson = require "cjson.safe"

-- Cache shared dict and config references
local dict = ngx.shared.cache
local config = ngx.shared.config
local admin_user = config:get("admin_user")
local admin_pass = config:get("admin_pass")
local guac_uri = config:get("guac_uri")
local guac_url = "http://127.0.0.1:8080" .. guac_uri .. "/api"

-- Function to check and close expired sessions
local function check_expired_sessions()

	local httpc = http.new()

	-- Obtain admin auth token from Guacamole
	local res, err = httpc:request_uri(guac_url .. "/tokens", {
		method = "POST",
		body = "username=" .. admin_user .. "&password=" .. admin_pass,
		headers = { ["Content-Type"] = "application/x-www-form-urlencoded" }
	})

	if not res or res.status ~= 200 then
		ngx.log(ngx.WARN, "Worker - Guacamole not ready or authentication failed (status: " .. 
			(res and res.status or "connection refused") .. "), will retry in 60s")
		return
	end

	local auth_data = cjson.decode(res.body)
	if not auth_data then
		ngx.log(ngx.ERR, "Worker - Failed to decode Guacamole auth response")
		return
	end

	local auth_token = auth_data.authToken
	local data_source = auth_data.dataSource

	if not auth_token then
		ngx.log(ngx.ERR, "Worker - Failed to obtain Guacamole admin token")
		return
	end

	-- Get list of active connections
	res, err = httpc:request_uri(guac_url .. "/session/data/" .. data_source .. 
			"/activeConnections?token=" .. auth_token, {
		method = "GET",
		headers = { ["Accept"] = "application/json" }
	})

	if not res or res.status ~= 200 then
		ngx.log(ngx.ERR, "Worker - Error retrieving active connections")
		return
	end

	local active_connections = cjson.decode(res.body)
	if not active_connections then
		ngx.log(ngx.WARN, "Worker - No active connections or failed to decode response")
		return
	end

	local now = ngx.time()

	-- Check each active connection for expiration
	for identifier, conn in pairs(active_connections) do
		local username = string.lower(conn.username)

		-- Get expiration time from shared dict
		local exp = dict:get("exp:" .. username)
		if now > tonumber(exp) then
			ngx.log(ngx.INFO, "Worker - Closing expired session (" .. identifier .. ") for " .. username)

			-- Terminate the active session
			local patch_body = cjson.encode({
			    { op = "remove", path = "/" .. identifier }
			})

			res, err = httpc:request_uri(guac_url .. "/session/data/" .. data_source .. 
					"/activeConnections?token=" .. auth_token, {
			    method = "PATCH",
			    body = patch_body,
			    headers = {
				["Content-Type"] = "application/json-patch+json",
			    }
			})

			if not res or res.status ~= 204 then
				ngx.log(ngx.ERR, "Worker - Error terminating connection for " .. username)
			else
				dict:delete("exp:" .. username)
				ngx.log(ngx.INFO, "Worker - Connection terminated for " .. username)
			end

			-- Obtain Guacamole's session token for revocation
			local user_token = dict:get("token:" .. username)
			if not user_token then
				ngx.log(ngx.DEBUG, "Worker - No token found for " .. username .. ", skipping revocation")
				goto continue
			end

			-- Revoke the Guacamole session token
			res, err = httpc:request_uri(guac_url .. "/tokens/" .. user_token .. 
					"?token=" .. auth_token, {
				method = "DELETE",
				headers = {}
			})

			if not res or res.status ~= 204 then
				ngx.log(ngx.ERR, "Worker - Error revoking Guacamole token for " .. username)
			end
		-- Always delete from dict to prevent memory leaks, even if revocation failed
		dict:delete("token:" .. username)
		dict:delete("guac_token:" .. user_token)  -- Clean up reverse mapping
		ngx.log(ngx.INFO, "Worker - Session token revoked for " .. username)			::continue::
		end
	end

end

-- Function to revoke sessions for users whose tunnels have closed
local function check_tunnel_closures()

	-- Early return if no pending closures (optimization to avoid unnecessary work)
	if not dict:get("has_pending_closures") then
		return
	end

	local httpc = http.new()

	-- Obtain admin auth token from Guacamole
	local res, err = httpc:request_uri(guac_url .. "/tokens", {
		method = "POST",
		body = "username=" .. admin_user .. "&password=" .. admin_pass,
		headers = { ["Content-Type"] = "application/x-www-form-urlencoded" }
	})

	if not res or res.status ~= 200 then
		ngx.log(ngx.WARN, "Worker - Guacamole not ready for tunnel closure check")
		return
	end

	local auth_data = cjson.decode(res.body)
	if not auth_data or not auth_data.authToken then
		ngx.log(ngx.ERR, "Worker - Failed to obtain Guacamole admin token for tunnel closure check")
		return
	end

	local auth_token = auth_data.authToken

	-- Get all keys matching pending_user:* (O(n) but only over pending users, not all dict keys)
	local keys = dict:get_keys(0)
	local has_more = false
	
	for _, key in ipairs(keys) do
		if key:match("^pending_user:") then
			has_more = true
			local username = key:sub(14)  -- Remove "pending_user:" prefix (13 chars + 1)
			local closed_time = dict:get("tunnel_closed:" .. username)
			
			-- Only process if the tunnel_closed marker still exists
			if closed_time then
				ngx.log(ngx.INFO, "Worker - Processing tunnel closure for user: " .. username)
				
				-- Get user's Guacamole session token for revocation
				local user_token = dict:get("token:" .. username)
				if not user_token then
					ngx.log(ngx.DEBUG, "Worker - No token found for " .. username .. ", skipping revocation")
					dict:delete("tunnel_closed:" .. username)  -- Clean up marker
					dict:delete(key)  -- Clean up pending_user marker
					goto continue_tunnel
				end

				-- Revoke the Guacamole session token
				res, err = httpc:request_uri(guac_url .. "/tokens/" .. user_token .. 
						"?token=" .. auth_token, {
					method = "DELETE",
					headers = {}
				})

				if not res or res.status ~= 204 then
					ngx.log(ngx.ERR, "Worker - Error revoking Guacamole token for " .. username)
				else
					ngx.log(ngx.INFO, "Worker - Session token revoked for " .. username .. " after tunnel closure")
				end
				
				-- Clean up dict entries
				dict:delete("token:" .. username)
				dict:delete("guac_token:" .. user_token)  -- Clean up reverse mapping
				dict:delete("tunnel_closed:" .. username)  -- Remove tunnel_closed marker
			end
			
			-- Always delete pending_user marker
			dict:delete(key)
		
			::continue_tunnel::
		end
	end

-- Clear flag if no more pending closures
if not has_more then
	dict:delete("has_pending_closures")
	ngx.log(ngx.DEBUG, "Worker - No more pending tunnel closures, flag cleared")
end

end

-- Delay first check to allow Guacamole to fully start (30 seconds)
local ok, err = ngx.timer.at(30, function(premature)
	if premature then return end
	
	-- After first check, set up periodic timer for expired sessions (30 seconds)
	local ok_periodic, err_periodic = ngx.timer.every(30, check_expired_sessions)
	if not ok_periodic then
		ngx.log(ngx.ERR, "Worker - Error initializing periodic timer for expired sessions: " .. tostring(err_periodic))
	else
		ngx.log(ngx.INFO, "Worker - Periodic expired session check initialized (every 30s)")
	end
	
	-- Set up periodic timer for tunnel closures (2 seconds)
	local ok_tunnel, err_tunnel = ngx.timer.every(2, check_tunnel_closures)
	if not ok_tunnel then
		ngx.log(ngx.ERR, "Worker - Error initializing periodic timer for tunnel closures: " .. tostring(err_tunnel))
	else
		ngx.log(ngx.INFO, "Worker - Periodic tunnel closure check initialized (every 2s)")
	end
	
	-- Run first checks immediately after delay (after setting up timers to ensure they're registered even if checks fail)
	check_expired_sessions()
	check_tunnel_closures()
end)

if not ok then
	ngx.log(ngx.ERR, "Worker - Error initializing delayed startup timer: " .. tostring(err))
end
