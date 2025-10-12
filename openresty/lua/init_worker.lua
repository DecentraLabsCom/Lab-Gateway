-- ============================================================================
-- init_worker.lua - Worker Initialization Phase (init_worker_by_lua)
-- ============================================================================
-- Runs once per worker process when it starts.
-- Purpose: Set up a periodic timer (every 60 seconds) that checks for expired
-- JWT sessions. For expired sessions, it terminates active Guacamole connections
-- and revokes Guacamole session tokens via the Guacamole REST API.
-- ============================================================================

local http = require "resty.http"
local cjson = require "cjson.safe"

local dict = ngx.shared.cache
local config = ngx.shared.config
local admin_user = config:get("admin_user")
local admin_pass = config:get("admin_pass")
local guac_uri = config:get("guac_uri")
local guac_url = "http://127.0.0.1:8080" .. guac_uri .. "/api"

-- Function to close active connections based on the information in the JWT
local function check_expired_sessions()

	local httpc = http.new()

	-- Obtain a session token from Guacamole (not the JWT)
	local res, err = httpc:request_uri(guac_url .. "/tokens", {
		method = "POST",
	        body = "username=" .. admin_user .. "&password=" .. admin_pass,
	        headers = { ["Content-Type"] = "application/x-www-form-urlencoded" }
	})

	if not res or res.status ~= 200 then
		ngx.log(ngx.ERR, "Error retrieving Guacamole's token.")
	        return
	end

	local auth_data = cjson.decode(res.body)
	local auth_token = auth_data.authToken
	local data_source = auth_data.dataSource

	if not auth_token then
		ngx.log(ngx.ERR, "Failed to obtain Guacamole's token.")
	        return
	end

	-- Get list of active connections
	res, err = httpc:request_uri(guac_url .. "/session/data/" .. data_source .. 
			"/activeConnections?token=" .. auth_token, {
		method = "GET",
		headers = { ["Accept"] = "application/json" }
	})

	if not res or res.status ~= 200 then
		ngx.log(ngx.ERR, "Error retrieving active connections.")
		return
	end

	local active_connections = cjson.decode(res.body)
	local now = ngx.time()

	for identifier, conn in pairs(active_connections) do
		local username = string.lower(conn.username)

		-- Get expiration time from shared dict
		local exp = dict:get("exp:" .. username)
		if not exp then
			ngx.log(ngx.ERR, "No expiration time found for ", username)
		elseif now > tonumber(exp) then
			ngx.log(ngx.INFO, "Closing expired session (" .. identifier  .. ") for ", username)

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
			    ngx.log(ngx.ERR, "Error terminating connection for " .. username)
			else
			    dict:delete("exp:" .. username)
			    ngx.log(ngx.INFO, "Connection terminated for " .. username)
			end

			-- Obtain Guacamole's session token for the user whose connection we have terminated
			local user_token = dict:get("token:" .. username)
			if not user_token then
				ngx.log(ngx.ERR, "No token found for " .. username)
				goto continue
			end

			-- Revoke the token
			res, err = httpc:request_uri(guac_url .. "/tokens/" .. user_token .. 
					"?token=" .. auth_token, {
				method = "DELETE",
				headers = {}
			})

			if not res or res.status ~= 204 then
				ngx.log(ngx.ERR, "Error revoking Guacamole's token.")
			end
			dict:delete("token:" .. username)
			ngx.log(ngx.INFO, "Session token revoked for " .. username)

			::continue::
		end
	end

end

-- Set a periodic execution (60 seconds - matches the timeout config set in guacamole.properties)
local ok, err = ngx.timer.every(60, check_expired_sessions)
if not ok then
	ngx.log(ngx.ERR, "Error initializing the timer.")
end
