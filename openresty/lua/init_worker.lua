-- ============================================================================
-- init_worker.lua - Worker Initialization Phase (init_worker_by_lua)
-- ============================================================================
-- Runs once per worker process when it starts.
-- Purpose: Set up a periodic timer (every 60 seconds) that checks for expired
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
		if not exp then
			ngx.log(ngx.DEBUG, "Worker - No expiration time found for " .. username)
		elseif now > tonumber(exp) then
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
			ngx.log(ngx.INFO, "Worker - Session token revoked for " .. username)
			
			::continue::
		end
	end

end

-- Delay first check to allow Guacamole to fully start (30 seconds)
local ok, err = ngx.timer.at(30, function(premature)
	if premature then return end
	
	-- After first check, set up periodic timer (60 seconds - matches guacamole.properties timeout)
	local ok_periodic, err_periodic = ngx.timer.every(60, check_expired_sessions)
	if not ok_periodic then
		ngx.log(ngx.ERR, "Worker - Error initializing periodic timer: " .. tostring(err_periodic))
	else
		ngx.log(ngx.INFO, "Worker - Periodic session check initialized (every 60s)")
	end
	
	-- Run first check immediately after delay
	check_expired_sessions()
end)

if not ok then
	ngx.log(ngx.ERR, "Worker - Error initializing delayed startup timer: " .. tostring(err))
end
