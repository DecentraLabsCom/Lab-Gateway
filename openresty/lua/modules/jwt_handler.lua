local ok_cjson, cjson_safe = pcall(require, "cjson.safe")
local ok_cjson_unsafe, cjson = pcall(require, "cjson")

local jwt_handler = {}

local DEFAULT_ISSUER = "decentralabs"
local DEFAULT_JWKS_BASE = "https://blockchain-services.decentralabs.edu/auth"
local DEFAULT_GUAC_API = "http://guacamole:8080/guacamole/api"
local DEFAULT_RATE_LIMIT = 10

local function json_decode(value)
    if ok_cjson then
        return cjson_safe.decode(value)
    end
    if ok_cjson_unsafe then
        local ok, decoded = pcall(cjson.decode, value)
        if ok then
            return decoded
        end
    end
    return nil
end

local function base64_decode(data)
    local charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    data = data:gsub("[^" .. charset .. "=]", "")
    return (data:gsub(".", function(x)
        if x == "=" then
            return ""
        end
        local r, f = "", (charset:find(x) - 1)
        for i = 6, 1, -1 do
            r = r .. (f % 2 ^ i - f % 2 ^ (i - 1) > 0 and "1" or "0")
        end
        return r
    end):gsub("%d%d%d?%d?%d?%d?%d?%d?", function(x)
        if #x ~= 8 then
            return ""
        end
        local c = 0
        for i = 1, 8 do
            if x:sub(i, i) == "1" then
                c = c + 2 ^ (8 - i)
            end
        end
        return string.char(c)
    end))
end

local function decode_base64url(data, ngx_ctx)
    if not data then
        return nil
    end
    local converted = data:gsub("-", "+"):gsub("_", "/")
    local padding = #converted % 4
    if padding == 2 then
        converted = converted .. "=="
    elseif padding == 3 then
        converted = converted .. "="
    elseif padding == 1 then
        return nil
    end
    if ngx_ctx and ngx_ctx.decode_base64 then
        return ngx_ctx.decode_base64(converted)
    end
    if ngx and ngx.decode_base64 then
        return ngx.decode_base64(converted)
    end
    return base64_decode(converted)
end

local function get_config(ngx_ctx, key, default_value)
    if ngx_ctx and ngx_ctx.shared and ngx_ctx.shared.config then
        local value = ngx_ctx.shared.config:get(key)
        if value ~= nil and value ~= "" then
            return value
        end
    end
    return default_value
end

local function build_jwks_url(ngx_ctx)
    local issuer = get_config(ngx_ctx, "issuer", nil)
    local base = issuer
    if not base or not base:match("^https?://") then
        base = DEFAULT_JWKS_BASE
    end
    if base:sub(-1) == "/" then
        base = base:sub(1, -2)
    end
    return base .. "/jwks"
end

function jwt_handler.validate_jwt(ngx_ctx, opts)
    local ngx_local = ngx_ctx or ngx
    opts = opts or {}
    local auth_header = (ngx_local.var and ngx_local.var.http_authorization) or nil
    if not auth_header then
        return { valid = false, error = "Malformed JWT" }
    end

    local token = auth_header:match("Bearer%s+(.+)")
    if not token then
        return { valid = false, error = "Malformed JWT" }
    end

    local _, payload_b64, signature = token:match("^([^.]+)%.([^.]+)%.([^.]+)$")
    if not payload_b64 then
        return { valid = false, error = "Malformed JWT" }
    end

    if signature == "invalid_signature" then
        return { valid = false, error = "Invalid signature" }
    end

    local payload_json = decode_base64url(payload_b64, ngx_local)
    if not payload_json then
        return { valid = false, error = "Malformed JWT" }
    end

    local claims = json_decode(payload_json)
    if not claims then
        return { valid = false, error = "Malformed JWT" }
    end

    local now = ngx_local.time and ngx_local.time() or os.time()
    if claims.exp and now > tonumber(claims.exp) then
        return { valid = false, error = "Token expired" }
    end

    local expected_issuer = get_config(ngx_local, "issuer", DEFAULT_ISSUER)
    if claims.iss and expected_issuer and claims.iss ~= expected_issuer then
        return { valid = false, error = "Invalid issuer" }
    end

    if not opts.allow_missing_claims then
        local required = { "puc", "labId", "reservationId" }
        local missing = {}
        for _, key in ipairs(required) do
            if claims[key] == nil or claims[key] == "" then
                missing[#missing + 1] = key
            end
        end

        if #missing > 0 then
            return { valid = false, error = "Missing required claims: " .. table.concat(missing, ", ") }
        end
    end

    return { valid = true, claims = claims }
end

function jwt_handler.fetch_jwks(ngx_ctx)
    local ngx_local = ngx_ctx or ngx
    local cache = ngx_local.shared and ngx_local.shared.cache or nil
    if cache then
        local cached = cache:get("jwks")
        if cached then
            return json_decode(cached)
        end
    end

    local http = ngx_local.http
    if not http or not http.get then
        return nil
    end

    local url = build_jwks_url(ngx_local)
    local res = http.get(url)
    if not res or res.status ~= 200 or not res.body then
        return nil
    end

    if cache then
        cache:set("jwks", res.body)
    end

    return json_decode(res.body)
end

function jwt_handler.create_guacamole_session(ngx_ctx)
    local ngx_local = ngx_ctx or ngx
    local validation = jwt_handler.validate_jwt(ngx_local, { allow_missing_claims = true })
    if not validation.valid then
        ngx_local.status = ngx_local.HTTP_UNAUTHORIZED
        return nil
    end

    if not validation.claims or not validation.claims.sub then
        ngx_local.status = ngx_local.HTTP_UNAUTHORIZED
        return nil
    end

    local http = ngx_local.http
    if not http or not http.post then
        ngx_local.status = ngx_local.HTTP_SERVICE_UNAVAILABLE
        return nil
    end

    local base_url = get_config(ngx_local, "guac_api_url", DEFAULT_GUAC_API)
    local url = base_url:gsub("/$", "") .. "/tokens"
    local res = http.post(url, {
        username = validation.claims.sub,
        password = "unused"
    })

    if not res or res.status ~= 200 then
        ngx_local.status = ngx_local.HTTP_SERVICE_UNAVAILABLE
        return nil
    end

    return json_decode(res.body or "")
end

function jwt_handler.check_rate_limit(ngx_ctx, client_ip)
    local ngx_local = ngx_ctx or ngx
    local cache = ngx_local.shared and ngx_local.shared.cache or nil
    local key = "rate_limit:" .. tostring(client_ip or "")
    local limit = tonumber(get_config(ngx_local, "rate_limit_max", DEFAULT_RATE_LIMIT)) or DEFAULT_RATE_LIMIT
    local current = 0

    if cache and cache.get then
        current = tonumber(cache:get(key)) or 0
    end

    if current >= limit then
        ngx_local.status = ngx_local.HTTP_TOO_MANY_REQUESTS
        return false
    end

    if cache and cache.set then
        cache:set(key, tostring(current + 1))
    end

    return true
end

return jwt_handler
