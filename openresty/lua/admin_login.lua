-- Password-style bootstrap for Gateway administrative sessions.
-- Tokens are accepted only in a POST body and are immediately replaced by
-- short-lived HttpOnly cookies scoped to the routes that need them.

local bit = require("bit")
local random = require("resty.random")
local resty_string = require("resty.string")

local function fail(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.say(message)
    return ngx.exit(status)
end

local function constant_time_eq(a, b)
    if type(a) ~= "string" or type(b) ~= "string" or #a ~= #b then
        return false
    end
    local result = 0
    for i = 1, #a do
        result = bit.bor(result, bit.bxor(string.byte(a, i), string.byte(b, i)))
    end
    return result == 0
end

if ngx.req.get_method() ~= "POST" then
    ngx.header["Allow"] = "POST"
    return fail(405, "Method not allowed")
end

local request_headers = ngx.req.get_headers()
local origin = request_headers["Origin"]
if origin and origin ~= "" then
    local expected_origin = (ngx.var.scheme or "https") .. "://" .. (ngx.var.http_host or ngx.var.host or "")
    if origin ~= expected_origin then
        return fail(403, "Cross-site administrative login is not allowed")
    end
end

local uri = ngx.var.uri or ""
local is_lab = uri == "/lab-manager/login"
local expected = is_lab and (os.getenv("LAB_MANAGER_TOKEN") or "")
    or (os.getenv("ADMIN_ACCESS_TOKEN") or "")
if expected == "" then
    return fail(503, "Administrative login is not configured")
end

ngx.req.read_body()
local args, err = ngx.req.get_post_args(2)
if not args or err then
    return fail(400, "Invalid login request")
end
local provided = args.token
if type(provided) ~= "string" or #provided == 0 or #provided > 512 then
    return fail(400, "Missing login token")
end
if not constant_time_eq(provided, expected) then
    return fail(401, "Invalid administrative token")
end
if provided:find("[;,%c]") then
    return fail(400, "Administrative token contains unsupported cookie characters")
end

local cookie_name = is_lab
    and (os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token")
    or (os.getenv("ADMIN_ACCESS_TOKEN_COOKIE") or "access_token")
local max_age = 900
-- Reject delimiters before creating the server-side session.  The browser
-- receives only the random session identifier, never the configured token.
local session_id = random.bytes(32, true)
if not session_id then
    return fail(503, "Administrative session service unavailable")
end
session_id = resty_string.to_hex(session_id)
local session_scope = is_lab and "lab" or "billing"
local session_cache = ngx.shared.cache
if not session_cache or not session_cache:set("admin_session:" .. session_scope .. ":" .. session_id, expected, max_age) then
    return fail(503, "Administrative session service unavailable")
end
local encoded = session_id
local cookies = {}
if is_lab then
    for _, path in ipairs({ "/lab-manager", "/lab-admin", "/ops", "/aas-admin" }) do
        cookies[#cookies + 1] = cookie_name .. "=" .. encoded
            .. "; Max-Age=" .. max_age .. "; Path=" .. path
            .. "; HttpOnly; Secure; SameSite=Lax"
    end
else
    for _, path in ipairs({ "/wallet", "/billing", "/wallet-dashboard", "/institution-config" }) do
        cookies[#cookies + 1] = cookie_name .. "=" .. encoded
            .. "; Max-Age=" .. max_age .. "; Path=" .. path
            .. "; HttpOnly; Secure; SameSite=Lax"
    end
end

ngx.header["Set-Cookie"] = cookies
ngx.header["Cache-Control"] = "no-store"
ngx.header["Referrer-Policy"] = "no-referrer"
ngx.status = 204
return ngx.exit(204)
