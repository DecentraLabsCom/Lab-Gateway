-- Strict Lab Manager admin guard.
-- Requires a valid LAB_MANAGER_TOKEN header or cookie for privileged admin routes.

local token = os.getenv("LAB_MANAGER_TOKEN") or ""
local header_name = os.getenv("LAB_MANAGER_TOKEN_HEADER") or "X-Lab-Manager-Token"
local cookie_name = os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token"

local function deny(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.say(message)
    return ngx.exit(status)
end

-- Constant-time string comparison to mitigate timing side-channels on token checks.
local function constant_time_eq(a, b)
    if type(a) ~= "string" or type(b) ~= "string" then
        return false
    end
    if #a ~= #b then
        return false
    end
    local result = 0
    for i = 1, #a do
        result = bit.bor(result, bit.bxor(string.byte(a, i), string.byte(b, i)))
    end
    return result == 0
end

if token == "" then
    return deny(ngx.HTTP_SERVICE_UNAVAILABLE, "Service unavailable: LAB_MANAGER_TOKEN is not configured.")
end

local headers = ngx.req.get_headers()
local provided = headers[header_name]

if not provided or provided == "" then
    local cookie_var = "cookie_" .. cookie_name
    provided = ngx.var[cookie_var]
end

if not provided or provided == "" then
    return deny(ngx.HTTP_UNAUTHORIZED, "Unauthorized: lab manager token required.")
end

if not constant_time_eq(provided, token) then
    return deny(ngx.HTTP_UNAUTHORIZED, "Unauthorized: invalid lab manager token.")
end

ngx.req.set_header(header_name, token)
