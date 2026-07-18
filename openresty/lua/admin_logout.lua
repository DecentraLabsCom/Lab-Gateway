local function cookie_header(name, path)
    return name .. "=; Max-Age=0; Path=" .. path .. "; HttpOnly; Secure; SameSite=Lax"
end

if ngx.req.get_method() ~= "POST" then
    ngx.header["Allow"] = "POST"
    ngx.status = 405
    return ngx.exit(405)
end

local request_headers = ngx.req.get_headers()
local origin = request_headers["Origin"]
if origin and origin ~= "" then
    local expected_origin = (ngx.var.scheme or "https") .. "://" .. (ngx.var.http_host or ngx.var.host or "")
    if origin ~= expected_origin then
        ngx.status = 403
        return ngx.exit(403)
    end
end

local admin_name = os.getenv("ADMIN_ACCESS_TOKEN_COOKIE") or "access_token"
local lab_name = os.getenv("LAB_MANAGER_TOKEN_COOKIE") or "lab_manager_token"
local cache = ngx.shared.cache
if cache then
    local billing_session = ngx.var["cookie_" .. admin_name]
    local lab_session = ngx.var["cookie_" .. lab_name]
    if billing_session and billing_session ~= "" then
        cache:delete("admin_session:billing:" .. billing_session)
        cache:delete("admin_csrf:billing:" .. billing_session)
    end
    if lab_session and lab_session ~= "" then
        cache:delete("admin_session:lab:" .. lab_session)
        cache:delete("admin_csrf:lab:" .. lab_session)
    end
end
local cookies = {}
for _, path in ipairs({ "/wallet", "/billing", "/wallet-dashboard", "/institution-config" }) do
    cookies[#cookies + 1] = cookie_header(admin_name, path)
end
for _, path in ipairs({ "/lab-manager", "/lab-admin", "/ops", "/aas-admin" }) do
    cookies[#cookies + 1] = cookie_header(lab_name, path)
end
ngx.header["Set-Cookie"] = cookies
ngx.header["Cache-Control"] = "no-store"
ngx.status = 204
return ngx.exit(204)
