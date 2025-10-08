local chunk = ngx.arg[1]
local eof = ngx.arg[2]

-- Accumulate response
ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")

-- Process when the response has finished
if eof then
	local cjson = require "cjson"
	local dict = ngx.shared.cache

	local body = ngx.ctx.response_body
	if not body:match("^%s*[{%[]") then
		ngx.log(ngx.ERR, "Response is not JSON, skipping.")
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
			-- Cannot call ngx.exit/say in body_filter phase; log and return silently
			return
		end
		ngx.log(ngx.INFO, "Session token stored for " .. decoded.username)
	end
end
