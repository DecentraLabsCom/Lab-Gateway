-- Preserve an explicit reservation ticket or provider bearer credential.
-- Requests without Authorization may use the scoped FMU_SESSION cookie.
if ngx.var.http_authorization and ngx.var.http_authorization ~= "" then
    return false
end

local handler = require "modules.fmu_access_handler"
return handler.run(ngx)
