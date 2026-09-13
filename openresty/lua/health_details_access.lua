-- Health diagnostics are operational data, not a public API. Reuse the
-- existing token/network policy used by Lab Manager operators.
-- Load the guard as a Lua function and invoke it from this chunk. Calling
-- dofile() directly would execute the guard through a C-call boundary, so an
-- ngx.exit() on an unauthorized request could not yield cleanly and would
-- close the connection without the intended 401 response body.
local guard = assert(loadfile("/etc/openresty/lua/lab_manager_access.lua"))
return guard()
