local ok_http, resty_http = pcall(require, "resty.http")
local ok_cjson, cjson_safe = pcall(require, "cjson.safe")
local ok_demo_guard, demo_guard = pcall(require, "modules.demo_guard")

local SessionGuard = {}
SessionGuard.__index = SessionGuard

-- Timer and TTL constants in seconds
local INITIAL_DELAY_SECONDS = 10
local EXPIRED_CHECK_INTERVAL = 10
local DEMO_CHECK_INTERVAL = 2
local DEMO_CHECK_TIMEOUT_MS = 3000
local TUNNEL_CHECK_INTERVAL = 2
local DEFAULT_GUAC_API = "http://guacamole:8080/guacamole/api"

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
    self.guac_api = opts.guac_api_url or self.config:get("guac_api_url") or DEFAULT_GUAC_API
    return self
end

local function token_cache_key(username)
    return "token:" .. username
end

local function token_reverse_cache_key(token)
    return "guac_token:" .. token
end

local function enforcement_expiry_cache_key(username)
    return "guac_enforcement_exp:" .. username
end

local function clear_cached_user_token(dict, username, user_token)
    if username and username ~= "" then
        dict:delete(token_cache_key(username))
        dict:delete(enforcement_expiry_cache_key(username))
        dict:delete("exp:" .. username)
    end
    if user_token then
        dict:delete(token_reverse_cache_key(user_token))
        dict:delete("guac_jwt_exp:" .. user_token)
        dict:delete("guac_jwt_last_seen:" .. user_token)
        dict:delete("guac_jti:" .. user_token)
        dict:delete("guac_reservation:" .. user_token)
        dict:delete("guac_demo:" .. user_token)
    end
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

local function revoke_user_token(self, httpc, auth_token, username, success_message)
    local ngx = self.ngx
    local user_token = self.dict:get(token_cache_key(username))
    if not user_token then
        ngx.log(ngx.DEBUG, "Worker - No token found for " .. username .. ", skipping revocation")
        return nil
    end

    local res = httpc:request_uri(self.guac_api .. "/tokens/" .. user_token .. "?token=" .. auth_token, {
        method = "DELETE",
        headers = {}
    })

    if not res or res.status ~= 204 then
        ngx.log(ngx.ERR, "Worker - Error revoking Guacamole token for " .. username)
        return false, user_token
    else
        ngx.log(ngx.INFO, string.format(success_message, username))
    end

    return true, user_token
end

local function iterate_expired_jwt_tokens(dict, now)
    local expired = {}
    for _, key in ipairs(dict:get_keys(0)) do
        if key:match("^guac_jwt_exp:") then
            local token = key:sub(14)
            local exp = tonumber(dict:get(key))
            if token ~= "" and exp and now >= exp then
                expired[#expired + 1] = token
            end
        end
    end
    return expired
end

local function iterate_demo_tokens(dict)
    local demo_tokens = {}
    for _, key in ipairs(dict:get_keys(0)) do
        if key:match("^guac_demo:") then
            local token = key:sub(11)
            if token ~= "" then
                demo_tokens[#demo_tokens + 1] = token
            end
        end
    end
    return demo_tokens
end

local function request_demo_availability(self, httpc, exp)
    local config = self.config
    local marketplace_url = config:get("marketplace_url") or ""
    local lab_id = config:get("demo_lab_id") or ""
    local now = self.ngx.time()
    local end_time = tonumber(exp)

    if marketplace_url == "" or lab_id == "" or not end_time or now + 1 >= end_time then
        return nil, "demo availability is not configured or has expired"
    end

    httpc:set_timeout(DEMO_CHECK_TIMEOUT_MS)
    local url = marketplace_url
        .. "/api/contract/reservation/checkAvailable"
        .. "?labId=" .. self.ngx.escape_uri(tostring(lab_id))
        .. "&start=" .. tostring(now + 1)
        .. "&end=" .. tostring(end_time)
    local res, err = httpc:request_uri(url, { method = "GET", ssl_verify = true })
    if err or not res or res.status ~= 200 then
        return nil, "availability authority unavailable"
    end

    local body, parse_err = self.cjson.decode(res.body or "")
    if parse_err or type(body) ~= "table" or type(body.isAvailable) ~= "boolean" then
        return nil, "availability authority returned invalid JSON"
    end

    return body.isAvailable == false, nil
end

local function revoke_explicit_token(self, httpc, auth_token, user_token, username)
    local display_username = username or "unknown JWT user"
    local res = httpc:request_uri(self.guac_api .. "/tokens/" .. user_token .. "?token=" .. auth_token, {
        method = "DELETE",
        headers = {}
    })
    if not res or res.status ~= 204 then
        self.ngx.log(self.ngx.ERR, "Worker - Error revoking expired Guacamole token for " .. display_username)
        return false
    end
    self.ngx.log(self.ngx.INFO, "Worker - Expired Guacamole token revoked for " .. display_username)
    return true
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

    local jwt_connection_close_failed = {}

    -- Close active tunnels first. JWT token revocation is handled below even
    -- when no tunnel exists; manual mappings retain their existing cleanup path.
    for identifier, conn in pairs(active_connections) do
        local username = string.lower(conn.username or "")
        local exp = dict:get(enforcement_expiry_cache_key(username))
        if exp and now >= tonumber(exp) then
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
                jwt_connection_close_failed[username] = true
            else
                ngx.log(ngx.INFO, "Worker - Connection terminated for " .. username)
                local user_token = dict:get(token_cache_key(username))
                if not user_token or not dict:get("guac_jwt_exp:" .. user_token) then
                    local revoked
                    revoked, user_token = revoke_user_token(
                        self, httpc, auth_token, username, "Worker - Session token revoked for %s"
                    )
                    if revoked or not user_token then
                        clear_cached_user_token(dict, username, user_token)
                    end
                end
            end
        end
    end

    -- guac_jwt_exp is the revocation queue: every expired auth token is
    -- revoked even when Guacamole reports no active connection for its user.
    for _, user_token in ipairs(iterate_expired_jwt_tokens(dict, now)) do
        local username = dict:get(token_reverse_cache_key(user_token))
        if not username or not jwt_connection_close_failed[username] then
            if revoke_explicit_token(self, httpc, auth_token, user_token, username) then
                clear_cached_user_token(dict, username, user_token)
            end
        end
    end
end

-- Demo access is not represented by a normal reservation, so an active demo
-- must be revoked when the authoritative reservation calendar becomes busy.
-- This is deliberately a separate, short polling loop: it bounds the race
-- window without making every reservation session query Marketplace.
function SessionGuard:check_demo_sessions()
    local dict = self.dict
    local ngx = self.ngx
    local demo_tokens = iterate_demo_tokens(dict)
    if #demo_tokens == 0 then
        return
    end

    local httpc = self.http_factory()
    local auth_token, data_source = request_guac_token(self, httpc)
    if not auth_token then
        return
    end

    local res, err = httpc:request_uri(self.guac_api .. "/session/data/" .. data_source
        .. "/activeConnections?token=" .. auth_token, {
        method = "GET",
        headers = { ["Accept"] = "application/json" }
    })
    if not res or res.status ~= 200 then
        ngx.log(ngx.ERR, "Worker - Error retrieving active connections for demo revocation")
        return
    end

    local active_connections = self.cjson.decode(res.body or "")
    if not active_connections then
        ngx.log(ngx.WARN, "Worker - Failed to decode active connections for demo revocation")
        return
    end

    local now = ngx.time()
    for _, user_token in ipairs(demo_tokens) do
        local exp = tonumber(dict:get("guac_jwt_exp:" .. user_token))
        if exp and now < exp then
            local busy, availability_err = request_demo_availability(self, httpc, exp)
            if availability_err then
                ngx.log(ngx.WARN, "Worker - " .. availability_err)
                -- Demo access is optional; do not keep it alive when its
                -- reservation authority cannot be verified.
                busy = true
            end
            if busy then
                local username = dict:get(token_reverse_cache_key(user_token))
                local close_failed = false

                for identifier, conn in pairs(active_connections) do
                    if username and string.lower(conn.username or "") == string.lower(username) then
                        local patch_body = self.cjson.encode({
                            { op = "remove", path = "/" .. identifier }
                        })
                        local close_res = httpc:request_uri(self.guac_api .. "/session/data/" .. data_source
                            .. "/activeConnections?token=" .. auth_token, {
                            method = "PATCH",
                            body = patch_body,
                            headers = { ["Content-Type"] = "application/json-patch+json" }
                        })
                        if not close_res or close_res.status ~= 204 then
                            close_failed = true
                            ngx.log(ngx.ERR, "Worker - Error terminating overlapping demo session for " .. username)
                        end
                    end
                end

                if not close_failed then
                    if revoke_explicit_token(self, httpc, auth_token, user_token, username) then
                        if ok_demo_guard then
                            demo_guard.release(self.ngx, dict:get("guac_jti:" .. user_token))
                        end
                        clear_cached_user_token(dict, username, user_token)
                    end
                end
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
            local revoked, user_token = revoke_user_token(
                self,
                httpc,
                auth_token,
                username,
                "Worker - Session token revoked for %s after tunnel closure"
            )
            if revoked or not user_token then
                clear_cached_user_token(dict, username, user_token)
                dict:delete("tunnel_closed:" .. username)
                dict:delete("pending_user:" .. username)
            end
        end
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

        local ok_demo, err_demo = ngx.timer.every(DEMO_CHECK_INTERVAL, function()
            -- Paid reservations can be confirmed after a demo handoff. Recheck
            -- the full remaining demo window and revoke overlapping sessions.
            self:check_demo_sessions()
        end)
        if not ok_demo then
            ngx.log(ngx.ERR, "Worker - Error initializing demo-session guard: " .. tostring(err_demo))
        else
            ngx.log(ngx.INFO, "Worker - Demo-session guard initialized (every " .. DEMO_CHECK_INTERVAL .. "s)")
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
        self:check_demo_sessions()
        self:check_tunnel_closures()
    end)

    if not ok then
        ngx.log(ngx.ERR, "Worker - Error initializing delayed startup timer: " .. tostring(err))
    end
end

return SessionGuard
