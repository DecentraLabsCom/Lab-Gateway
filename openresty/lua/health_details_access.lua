-- Health diagnostics are operational data, not a public API. Reuse the
-- existing token/network policy used by Lab Manager operators.
return dofile("/etc/openresty/lua/lab_manager_access.lua")
