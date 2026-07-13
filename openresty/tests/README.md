# OpenResty Lua Unit Tests

This folder contains unit tests for the Lua modules used by OpenResty.

## Test structure

```text
openresty/tests/
|- run.lua
|- run-lua-tests.sh
|- run-lua-tests.ps1
|- helpers/
|  |- runner.lua
|  |- ngx_stub.lua
|  `- http_client_stub.lua
`- unit/
   |- access_handler_spec.lua
   |- access_handler_extended_spec.lua
   |- guacamole_token_handler_spec.lua
   |- header_filter_handler_spec.lua
   |- header_filter_handler_extended_spec.lua
   |- admin_access_spec.lua
   |- treasury_access_spec.lua
   |- jwt_handler_spec.lua
   |- lab_manager_access_spec.lua
   |- log_handler_spec.lua
   |- log_handler_extended_spec.lua
   |- session_guard_spec.lua
   `- session_guard_extended_spec.lua
```

## Run tests

Linux/macOS:

```bash
./openresty/tests/run-lua-tests.sh
./openresty/tests/run-jwt-key-sync-integration.sh
```

Windows (PowerShell):

```powershell
.\openresty\tests\run-lua-tests.ps1
.\openresty\tests\run-jwt-key-sync-integration.ps1
```

Direct run (if LuaJIT + lua-cjson are installed):

```bash
luajit openresty/tests/run.lua
```

## Coverage focus

- Access/session propagation (`access_handler`, `treasury_access`, `lab_manager_access`)
- JWT validation and JWKS fetch (`jwt_handler`)
- Content-phase Guacamole token exchange and clean redirect filtering
- Session cleanup and revocation (`log_handler`, `session_guard`)
- Lite-mode JWT key synchronization from `ISSUER` origin (`run-jwt-key-sync-integration.*`)

## Add a new spec

1. Create a file in `openresty/tests/unit/`.
2. Register it in `openresty/tests/run.lua`.
3. Run the suite.
