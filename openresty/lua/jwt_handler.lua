local jwt_handler = {}

-- Mock JWT handler module for testing
-- This is a basic implementation to support the test suite

local cjson = require "cjson"
local ngx = ngx or {
    log = function(level, msg) print("[" .. level .. "] " .. msg) end,
    HTTP_UNAUTHORIZED = 401,
    HTTP_BAD_REQUEST = 400,
    HTTP_SERVICE_UNAVAILABLE = 503,
    exit = function(code) error("ngx.exit(" .. code .. ")") end,
    say = function(msg) print(msg) end,
    header = {},
    var = {},
    req = {
        get_headers = function() return {} end,
        get_method = function() return "GET" end
    },
    shared = {
        DICT = {}
    }
}

-- Constants
local LOG_LEVELS = {
    ERR = ngx.ERR,
    WARN = ngx.WARN,
    INFO = ngx.INFO,
    DEBUG = ngx.DEBUG
}

-- Configuration
local config = {
    jwt_secret = "test-secret-key",
    jwt_issuer = "test-issuer",
    jwt_audience = "test-audience",
    rate_limit_window = 60,
    rate_limit_max_requests = 100,
    session_timeout = 3600
}

-- JWKS cache
local jwks_cache = {}

-- Session store (mock)
local sessions = {}

-- Rate limiting store (mock)
local rate_limits = {}

-- Validate JWT token
function jwt_handler.validate_token(token)
    if not token or token == "" then
        return false, "Missing token"
    end

    -- Mock validation logic
    if token == "valid.jwt.token" then
        return true, {
            sub = "user123",
            exp = os.time() + 3600,
            iat = os.time(),
            iss = config.jwt_issuer,
            aud = config.jwt_audience,
            scope = "read write"
        }
    elseif token == "expired.jwt.token" then
        return false, "Token expired"
    elseif token == "invalid.jwt.token" then
        return false, "Invalid signature"
    elseif token == "malformed.jwt.token" then
        return false, "Malformed token"
    else
        return false, "Invalid token"
    end
end

-- Fetch JWKS from endpoint
function jwt_handler.fetch_jwks(url)
    if url == "https://valid.jwks.endpoint" then
        return {
            keys = {
                {
                    kty = "RSA",
                    use = "sig",
                    kid = "test-key-id",
                    n = "test-modulus",
                    e = "AQAB"
                }
            }
        }
    elseif url == "https://invalid.jwks.endpoint" then
        error("HTTP request failed")
    else
        return nil, "Invalid JWKS endpoint"
    end
end

-- Create Guacamole session
function jwt_handler.create_guacamole_session(user_id, lab_id)
    local session_id = "session_" .. user_id .. "_" .. lab_id .. "_" .. os.time()
    sessions[session_id] = {
        user_id = user_id,
        lab_id = lab_id,
        created = os.time(),
        active = true
    }
    return session_id
end

-- Check rate limit
function jwt_handler.check_rate_limit(client_ip)
    local key = client_ip .. "_" .. math.floor(os.time() / config.rate_limit_window)
    local current = rate_limits[key] or 0

    if current >= config.rate_limit_max_requests then
        return false, "Rate limit exceeded"
    end

    rate_limits[key] = current + 1
    return true
end

-- Validate session
function jwt_handler.validate_session(session_id)
    local session = sessions[session_id]
    if not session then
        return false, "Session not found"
    end

    if not session.active then
        return false, "Session inactive"
    end

    if os.time() - session.created > config.session_timeout then
        session.active = false
        return false, "Session expired"
    end

    return true, session
end

-- Process JWT authentication
function jwt_handler.process_auth()
    local auth_header = ngx.req.get_headers()["Authorization"]
    if not auth_header then
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
        return
    end

    local token = auth_header:match("Bearer%s+(.+)")
    if not token then
        ngx.exit(ngx.HTTP_BAD_REQUEST)
        return
    end

    -- Check rate limit
    local client_ip = ngx.var.remote_addr or "127.0.0.1"
    local allowed, err = jwt_handler.check_rate_limit(client_ip)
    if not allowed then
        ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
        return
    end

    -- Validate token
    local valid, claims_or_error = jwt_handler.validate_token(token)
    if not valid then
        ngx.log(LOG_LEVELS.ERR, "JWT validation failed: " .. claims_or_error)
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
        return
    end

    -- Create session
    local session_id = jwt_handler.create_guacamole_session(claims_or_error.sub, "lab123")

    -- Set headers
    ngx.header["X-Session-ID"] = session_id
    ngx.header["X-User-ID"] = claims_or_error.sub
end

return jwt_handler