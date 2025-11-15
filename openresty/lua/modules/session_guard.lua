local ok_http, resty_http = pcall(require, "resty.http")
local ok_cjson, cjson_safe = pcall(require, "cjson.safe")

local SessionGuard = {}
SessionGuard.__index = SessionGuard

-- Timer and TTL constants in seconds
local INITIAL_DELAY_SECONDS = 30
local EXPIRED_CHECK_INTERVAL = 30
local TUNNEL_CHECK_INTERVAL = 2

local function default_http_factory()
    if not ok_http then
        error("resty.http not available; provide a custom http_factory")
    end
    return resty_http.new()
end

local function default_decoder()
    if not ok_cjson then
        error("cjson.safe not available; provide a custom cjson implementation")
    end
    return cjson_safe
end

function SessionGuard.new(opts)
    opts = opts or {}
    local ngx_ctx = opts.ngx or ngx

    local self = setmetatable({}, SessionGuard)
    self.ngx = ngx_ctx
    self.dict = opts.dict or ngx_ctx.shared.cache
    self.config = opts.config or ngx_ctx.shared.config
    self.http_factory = opts.http_factory or default_http_factory
    self.cjson = opts.cjson or default_decoder()
    self.admin_user = opts.admin_user or self.config:get("admin_user")
    self.admin_pass = opts.admin_pass or self.config:get("admin_pass")
    self.guac_uri = opts.guac_uri or (self.config:get("guac_uri") or "/guacamole")
    local default_api = "http://127.0.0.1:8080" .. self.guac_uri .. "/api"
    self.guac_api = opts.guac_api_url or self.config:get("guac_api_url") or default_api
    return self
end

local function request_guac_token(self, httpc)
    local ngx = self.ngx
    local res, err = httpc:request_uri(self.guac_api .. "/tokens", {
        method = "POST",
        body = "username=" .. self.admin_user .. "&password=" .. self.admin_pass,
        headers = { ["Content-Type"] = "application/x-www-form-urlencoded" }
    })

    if not res or res.status ~= 200 then
        ngx.log(ngx.WARN, "Worker - Guacamole not ready or authentication failed (status: " ..
            (res and res.status or "connection refused") .. ")")
        return nil
    end

    local auth_data = self.cjson.decode(res.body or "")
    if not auth_data or not auth_data.authToken then
        ngx.log(ngx.ERR, "Worker - Failed to decode Guacamole auth response")
        return nil
    end

    return auth_data.authToken, auth_data.dataSource
end

function SessionGuard:check_expired_sessions()
    local ngx = self.ngx
    local dict = self.dict
    local httpc = self.http_factory()
    local auth_token, data_source = request_guac_token(self, httpc)
    if not auth_token then
        return
    end

    local res, err = httpc:request_uri(self.guac_api .. "/session/data/" .. data_source ..
        "/activeConnections?token=" .. auth_token, {
        method = "GET",
        headers = { ["Accept"] = "application/json" }
    })

    if not res or res.status ~= 200 then
        ngx.log(ngx.ERR, "Worker - Error retrieving active connections")
        return
    end

    local active_connections = self.cjson.decode(res.body or "")
    if not active_connections then
        ngx.log(ngx.WARN, "Worker - No active connections or failed to decode response")
        return
    end

    local now = ngx.time()

    -- Iterate over Guacamole's active connections and revoke those whose JWT payload expired.
    for identifier, conn in pairs(active_connections) do
        local username = string.lower(conn.username or "")
        local exp = dict:get("exp:" .. username)
        if exp and now > tonumber(exp) then
            ngx.log(ngx.INFO, "Worker - Closing expired session (" .. identifier .. ") for " .. username)

            local patch_body = self.cjson.encode({
                { op = "remove", path = "/" .. identifier }
            })

            res, err = httpc:request_uri(self.guac_api .. "/session/data/" .. data_source ..
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

            local user_token = dict:get("token:" .. username)
            if not user_token then
                ngx.log(ngx.DEBUG, "Worker - No token found for " .. username .. ", skipping revocation")
            else
                res, err = httpc:request_uri(self.guac_api .. "/tokens/" .. user_token ..
                    "?token=" .. auth_token, {
                    method = "DELETE",
                    headers = {}
                })

                if not res or res.status ~= 204 then
                    ngx.log(ngx.ERR, "Worker - Error revoking Guacamole token for " .. username)
                else
                    ngx.log(ngx.INFO, "Worker - Session token revoked for " .. username)
                end
                dict:delete("token:" .. username)
                dict:delete("guac_token:" .. user_token)
            end
        end
    end
end

local function iterate_pending_users(dict)
    local keys = dict:get_keys(0)
    local pending = {}
    for _, key in ipairs(keys) do
        if key:match("^pending_user:") then
            pending[#pending + 1] = key:sub(14)
        end
    end
    return pending
end

function SessionGuard:check_tunnel_closures()
    local dict = self.dict
    local ngx = self.ngx

    -- Early exit keeps this worker lightweight when no tunnels closed recently.
    if not dict:get("has_pending_closures") then
        return
    end

    local httpc = self.http_factory()
    local auth_token = request_guac_token(self, httpc)
    if not auth_token then
        ngx.log(ngx.WARN, "Worker - Guacamole not ready for tunnel closure check")
        return
    end

    local users = iterate_pending_users(dict)

    -- Each pending user entry represents a manual (non-JWT) tunnel closure detected by log.lua.
    for _, username in ipairs(users) do
        local closed_time = dict:get("tunnel_closed:" .. username)

        if closed_time then
            ngx.log(ngx.INFO, "Worker - Processing tunnel closure for user: " .. username)
            local user_token = dict:get("token:" .. username)
            if not user_token then
                ngx.log(ngx.DEBUG, "Worker - No token found for " .. username .. ", skipping revocation")
            else
                local res, err = httpc:request_uri(self.guac_api .. "/tokens/" .. user_token ..
                    "?token=" .. auth_token, {
                    method = "DELETE",
                    headers = {}
                })

                if not res or res.status ~= 204 then
                    ngx.log(ngx.ERR, "Worker - Error revoking Guacamole token for " .. username)
                else
                    ngx.log(ngx.INFO, "Worker - Session token revoked for " .. username .. " after tunnel closure")
                end
            end

            local user_token = dict:get("token:" .. username)
            dict:delete("token:" .. username)
            if user_token then
                dict:delete("guac_token:" .. user_token)
            end
            dict:delete("tunnel_closed:" .. username)
        end

        dict:delete("pending_user:" .. username)
    end

    if #iterate_pending_users(dict) == 0 then
        dict:delete("has_pending_closures")
        ngx.log(ngx.DEBUG, "Worker - No more pending tunnel closures, flag cleared")
    end
end

function SessionGuard:start()
    local ngx = self.ngx
    local ok, err = ngx.timer.at(INITIAL_DELAY_SECONDS, function(premature)
        if premature then
            return
        end

        local ok_periodic, err_periodic = ngx.timer.every(EXPIRED_CHECK_INTERVAL, function()
            -- Guard against JWT expirations taking effect while a user is still connected.
            self:check_expired_sessions()
        end)
        if not ok_periodic then
            ngx.log(ngx.ERR, "Worker - Error initializing periodic timer for expired sessions: " .. tostring(err_periodic))
        else
            ngx.log(ngx.INFO, "Worker - Periodic expired session check initialized (every " .. EXPIRED_CHECK_INTERVAL .. "s)")
        end

        local ok_tunnel, err_tunnel = ngx.timer.every(TUNNEL_CHECK_INTERVAL, function()
            -- Consume tunnel closure markers quickly so manual sessions are revoked promptly.
            self:check_tunnel_closures()
        end)
        if not ok_tunnel then
            ngx.log(ngx.ERR, "Worker - Error initializing periodic timer for tunnel closures: " .. tostring(err_tunnel))
        else
            ngx.log(ngx.INFO, "Worker - Periodic tunnel closure check initialized (every " .. TUNNEL_CHECK_INTERVAL .. "s)")
        end

        self:check_expired_sessions()
        self:check_tunnel_closures()
    end)

    if not ok then
        ngx.log(ngx.ERR, "Worker - Error initializing delayed startup timer: " .. tostring(err))
    end
end

return SessionGuard
