-- ============================================================================
-- body_filter.lua - Body Filter Phase (body_filter_by_lua)
-- ============================================================================
-- Runs when processing response BODY chunks from Guacamole (after headers).
-- Purpose: Capture Guacamole's JSON authentication response containing
-- authToken and username. Stores the authToken in shared dict so that
-- init_worker can later revoke it when the JWT session expires.
-- ============================================================================

local chunk = ngx.arg[1]
local eof = ngx.arg[2]

-- Accumulate response
ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")

-- Process when the response has finished
if eof then
	local cjson = require "cjson"
	local dict = ngx.shared.cache
	
	-- Check Content-Type header
	local content_type = ngx.header["Content-Type"]
	if not content_type or not content_type:match("application/json") then
		ngx.log(ngx.INFO, "Body filter - Skipping non-JSON response (Content-Type: " .. tostring(content_type) .. ")")
		return
	end

	-- Check body
	local body = ngx.ctx.response_body
	if not body or body == "" then
		ngx.log(ngx.WARN, "Response body is empty, skipping.")
		return
	end
	if not body:match("^%s*[{%[]") then
		ngx.log(ngx.ERR, "Response is not JSON, skipping. Body preview: " .. body:sub(1, 200))
		return
	end

	local success, decoded = pcall(cjson.decode, body)
	if not success then
        	ngx.log(ngx.ERR, "JSON decode error: ", decoded)
		return
	end

	if decoded and decoded.authToken and decoded.username then
		-- Store the session token for this user
		local ok, err = dict:set("token:" .. string.lower(decoded.username), decoded.authToken, 7200)
		if not ok then
			ngx.log(ngx.ERR, "Error when registering token in shared dict: " .. tostring(err))
			return
		end
		ngx.log(ngx.INFO, "Session token stored for " .. decoded.username)
	end
end
