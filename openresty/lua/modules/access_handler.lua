local _M = {}

local demo_guard = require "modules.demo_guard"

local DEFAULT_JWT_GUAC_IDLE_TIMEOUT_SECONDS = 60
local DEFAULT_MANUAL_GUAC_IDLE_TIMEOUT_SECONDS = 60

local function jwt_guac_exp_key(token)
    return "guac_jwt_exp:" .. token
end

local function jwt_guac_last_seen_key(token)
    return "guac_jwt_last_seen:" .. token
end

local function manual_guac_last_seen_key(token)
    return "guac_manual_last_seen:" .. token
end

local function get_jwt_guac_idle_timeout(config)
    local configured = config and tonumber(config:get("jwt_guac_idle_timeout_seconds"))
    if configured and configured > 0 then
        return configured
    end
    return DEFAULT_JWT_GUAC_IDLE_TIMEOUT_SECONDS
end

local function get_manual_guac_idle_timeout(config)
    local configured = config and tonumber(config:get("manual_guac_idle_timeout_seconds"))
    if configured and configured > 0 then
        return configured
    end
    return DEFAULT_MANUAL_GUAC_IDLE_TIMEOUT_SECONDS
end

local function reject_jwt_guac_token(ngx, token, reason)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Unauthorized: Guacamole JWT session expired")
    ngx.log(ngx.INFO, "Access - Rejected Guacamole JWT auth token: " .. reason)
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
    return true
end

local function reject_manual_guac_token(ngx, token, reason)
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Unauthorized: Guacamole manual session expired")
    ngx.log(ngx.INFO, "Access - Rejected Guacamole manual auth token: " .. reason)
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
    return true
end

local function enforce_jwt_guac_token_timeout(ngx, dict)
    local token = ngx.var.arg_token
    if not token or token == "" then
        return false
    end

    local exp = tonumber(dict:get(jwt_guac_exp_key(token)))
    if not exp then
        return false
    end

    local now = ngx.time()
    if now > exp then
        return reject_jwt_guac_token(ngx, token, "JWT expired")
    end

    local idle_timeout = get_jwt_guac_idle_timeout(ngx.shared.config)
    local last_seen = tonumber(dict:get(jwt_guac_last_seen_key(token)))
    if last_seen and (now - last_seen) > idle_timeout then
        return reject_jwt_guac_token(ngx, token, "idle timeout exceeded")
    end

    dict:set(jwt_guac_last_seen_key(token), now, 7200)
    return false
end

local function enforce_manual_guac_token_timeout(ngx, dict)
    local token = ngx.var.arg_token
    if not token or token == "" then
        return false
    end

    if dict:get(jwt_guac_exp_key(token)) then
        return false
    end

    local username = dict:get("guac_token:" .. token)
    if not username or username == "" then
        return false
    end

    local config = ngx.shared.config
    local admin_user = config and config:get("admin_user")
    if admin_user and string.lower(username) == string.lower(admin_user) then
        return false
    end

    local now = ngx.time()
    local last_seen_key = manual_guac_last_seen_key(token)
    local last_seen = tonumber(dict:get(last_seen_key))
    if last_seen and (now - last_seen) > get_manual_guac_idle_timeout(config) then
        return reject_manual_guac_token(ngx, token, "idle timeout exceeded")
    end

    dict:set(last_seen_key, now, 7200)
    return false
end

---Processes the access phase logic that validates the JTI cookie and
-- propagates the username to Guacamole when it is still valid.
-- When no JTI cookie is present the JWT supplied via the ?jwt= query
-- parameter is validated directly so that the very first request to
-- Guacamole already carries the Authorization header, preventing the
-- Angular SPA from showing the login screen.
-- @param ngx_ctx table Optional ngx-like context (defaults to global ngx).
-- @param deps    table Optional dependency overrides (e.g. { jwt = stub }).
function _M.run(ngx_ctx, deps)
    local ngx = ngx_ctx or ngx
    local dict = ngx.shared.cache

    if enforce_jwt_guac_token_timeout(ngx, dict) then
        return
    end
    if enforce_manual_guac_token_timeout(ngx, dict) then
        return
    end

    -- ── Path 1: JTI cookie present ─────────────────────────────────────────
    -- Only uses the cookie fast-path when the JTI is still live in the shared
    -- dict.  A stale or unknown JTI (e.g. after a gateway restart wipes the
    -- dict) falls through to Path 2 so a fresh ?jwt= token in the URL can
    -- still authenticate the user on the very same request.
    local cookies = ngx.var.http_cookie
    if cookies and cookies ~= "" then
        local jti = string.match(cookies, "JTI=([^;]+)")
        if jti and jti ~= "" then
            local username = dict:get("username:" .. jti)
            if username then
                local exp = dict:get("exp:" .. username)
                if exp then
                    local now = ngx.time()
                    if now <= tonumber(exp) then
                        ngx.req.set_header("Authorization", username)
                        ngx.ctx.jwt_authenticated = true
                        ngx.ctx.jwt_username = username
                        ngx.ctx.jwt_jti = jti
                        ngx.ctx.jwt_reservation_key = dict:get("reservation:" .. jti)
                        ngx.ctx.jwt_exp = tonumber(exp)
                        ngx.log(ngx.INFO, "Access - Valid cookie. Authorization header set for " .. username)
                        demo_guard.run(ngx)
                        return
                    end
                    ngx.log(ngx.INFO, "Access - JWT expired for user: " .. username .. " – falling through to JWT URL path")
                else
                    ngx.log(ngx.WARN, "Access - No expiration for user: " .. username .. " – falling through to JWT URL path")
                end
            else
                ngx.log(ngx.DEBUG, "Access - JTI cookie not in cache (stale?) – falling through to JWT URL path")
            end
            -- Fall through to Path 2 in all failure cases above.
        end
    end

    -- ── Path 2: No JTI cookie – fall back to ?jwt= query parameter ─────────
    -- Validates the JWT so the Authorization header reaches Guacamole on the
    -- very first request, avoiding the login-screen flash.
    local token = ngx.var.arg_jwt
    if not token or token == "" then
        ngx.log(ngx.DEBUG, "Access - No cookie and no JWT found. Proceeding unauthenticated.")
        return
    end

    local jwt = (deps and deps.jwt) or require "resty.jwt"

    local jwt_object = jwt:load_jwt(token)
    if not jwt_object.valid then
        ngx.log(ngx.WARN, "Access - Invalid JWT format: " .. tostring(jwt_object.reason))
        return
    end

    local public_key = dict:get("public_key")
    if not public_key then
        ngx.log(ngx.ERR, "Access - Public key not available; skipping JWT verification")
        return
    end

    local jwt_obj = jwt:verify_jwt_obj(public_key, jwt_object)
    if not jwt_obj or not jwt_obj.verified then
        ngx.log(ngx.WARN, "Access - JWT verification failed: " .. tostring(jwt_obj and jwt_obj.reason or "unknown"))
        return
    end

    local jti = jwt_obj.payload.jti
    if not jti then
        ngx.log(ngx.WARN, "Access - JTI claim missing in JWT")
        return
    end

    local username = jwt_obj.payload.sub
    if not username then
        ngx.log(ngx.WARN, "Access - Username (sub) claim missing in JWT")
        return
    end
    local username_lower = string.lower(username)

    local config = ngx.shared.config
    local req_issuer = config:get("issuer")
    local issuer = jwt_obj.payload.iss
    if not issuer or issuer ~= req_issuer then
        ngx.log(ngx.WARN, "Access - Invalid issuer claim: " .. tostring(issuer) ..
            " (expected: " .. tostring(req_issuer) .. ")")
        return
    end

    local https_port = config:get("https_port")
    local port_suffix = (https_port == "443") and "" or (":" .. https_port)
    local req_audience = "https://" .. config:get("server_name") .. port_suffix .. config:get("guac_uri")
    local audience = jwt_obj.payload.aud

    local function normalize_audience(url)
        if not url or url == "" then return url end
        return url:gsub("/+$", "")
    end

    if normalize_audience(audience) ~= normalize_audience(req_audience) then
        ngx.log(ngx.WARN, "Access - Invalid audience claim: " .. tostring(audience) ..
            " (expected: " .. req_audience .. ")")
        return
    end

    -- Store session data so that header_filter_handler can set the JTI cookie
    -- on the response without re-doing the full JWT validation.
    dict:set("username:" .. jti, username_lower, 7200)
    dict:set("exp:" .. username_lower, jwt_obj.payload.exp, 7200)
    if jwt_obj.payload.reservationKey then
        dict:set("reservation:" .. jti, jwt_obj.payload.reservationKey, 7200)
    end

    ngx.req.set_header("Authorization", username_lower)
    ngx.ctx.jwt_authenticated = true
    ngx.ctx.jwt_username = username_lower
    ngx.ctx.jwt_jti = jti
    ngx.ctx.jwt_reservation_key = jwt_obj.payload.reservationKey
    ngx.ctx.jwt_exp = jwt_obj.payload.exp
    ngx.log(ngx.INFO, "Access - JWT validated from URL. Authorization header set for " .. username_lower)
    demo_guard.run(ngx)
end

return _M
