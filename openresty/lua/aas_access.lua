-- Enforce the trust boundary for the AAS upstream.
--
-- The bundled BaSyx service is reachable only on the internal fmu_aas network.
-- Any explicitly configured external endpoint must use HTTPS, be present in the
-- exact hostname allowlist, and receive a dedicated service credential. Client
-- Authorization headers are never forwarded to an AAS server.

local config = ngx.shared.config
local bundled_url = "http://basyx-aas-server:8081"

local lite_mode = config and config:get("lite_mode")
if lite_mode == 1 or lite_mode == true or lite_mode == "1" then
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Forbidden: AAS endpoints are not available in Lite mode.")
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

local upstream = (config and config:get("basyx_aas_url")) or bundled_url
upstream = tostring(upstream):gsub("/+%s*$", "")

local function reject(message)
    ngx.log(ngx.ERR, "AAS upstream policy rejected request: ", message)
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json"
    ngx.say('{"error":"AAS upstream policy unavailable"}')
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

local function parse_origin(url)
    local scheme, authority = url:match("^(https?)://([^/%?#]+)")
    if not scheme or not authority or authority == "" then
        return nil, "invalid URL"
    end
    if authority:find("@", 1, true) then
        return nil, "userinfo is not permitted"
    end

    local host
    if authority:sub(1, 1) == "[" then
        host = authority:match("^%[([^%]]+)%]")
    else
        host = authority:match("^([^:]+)")
    end
    host = host and host:lower() or nil
    if not host or host == "" then
        return nil, "missing hostname"
    end
    return { scheme = scheme:lower(), host = host }
end

local function allowed_host(host)
    local configured = os.getenv("AAS_ALLOWED_HOSTS") or ""
    for value in configured:gmatch("([^,]+)") do
        value = value:gsub("^%s*(.-)%s*$", "%1"):lower()
        if value ~= "" and value == host then
            return true
        end
    end
    return false
end

-- Never pass a caller's bearer/JWT to BaSyx, including for the bundled service.
ngx.req.set_header("Authorization", nil)

if upstream == bundled_url then
    return
end

local origin, parse_error = parse_origin(upstream)
if not origin then
    return reject(parse_error or "invalid URL")
end
if origin.scheme ~= "https" then
    return reject("external AAS endpoint must use HTTPS")
end
if not allowed_host(origin.host) then
    return reject("external AAS hostname is not allowlisted")
end

local token = os.getenv("AAS_SERVICE_TOKEN") or ""
local token_lc = token:lower()
if token == "" or token_lc == "change_me" or token_lc == "changeme" or token_lc == "password" or token_lc == "test" then
    return reject("AAS_SERVICE_TOKEN is missing")
end

local header_name = os.getenv("AAS_SERVICE_TOKEN_HEADER") or "Authorization"
header_name = header_name:gsub("^%s*(.-)%s*$", "%1")
if not header_name:match("^[A-Za-z][A-Za-z0-9-]*$") then
    return reject("invalid AAS_SERVICE_TOKEN_HEADER")
end

if header_name:lower() == "authorization" then
    ngx.req.set_header(header_name, "Bearer " .. token)
else
    ngx.req.set_header(header_name, token)
end
