# OpenResty Lua Unit Tests

This directory contains unit tests for the OpenResty Lua modules in the Lab Gateway project.

## Test Structure

```
openresty/tests/
├── run.lua                     # Main test runner
├── run-lua-tests.sh           # Shell script runner (Linux/Mac)
├── run-lua-tests.ps1          # PowerShell script runner (Windows)
├── helpers/
│   ├── runner.lua             # Custom test framework
│   ├── ngx_stub.lua           # Mock ngx object
│   └── http_client_stub.lua   # Mock HTTP client
└── unit/
    ├── access_handler_spec.lua
    ├── access_handler_extended_spec.lua
    ├── body_filter_handler_spec.lua
    ├── body_filter_handler_extended_spec.lua
    ├── header_filter_handler_spec.lua
    ├── header_filter_handler_extended_spec.lua
    ├── log_handler_spec.lua
    ├── log_handler_extended_spec.lua
    ├── session_guard_spec.lua
    └── session_guard_extended_spec.lua
```

## Running Tests

### Using Docker (Recommended)

The tests can be run in a Docker container with all dependencies:

**Linux/Mac:**
```bash
./openresty/tests/run-lua-tests.sh
```

**Windows (PowerShell):**
```powershell
.\openresty\tests\run-lua-tests.ps1
```

### Direct Execution (requires LuaJIT + lua-cjson)

From the project root:
```bash
cd openresty
luajit tests/run.lua
```

## Test Coverage

### Modules Tested

| Module | Test File | Coverage |
|--------|-----------|----------|
| `access_handler.lua` | `access_handler_spec.lua`, `access_handler_extended_spec.lua` | Cookie parsing, JTI validation, session expiration |
| `header_filter_handler.lua` | `header_filter_handler_spec.lua`, `header_filter_handler_extended_spec.lua` | JWT validation, cookie setting, redirect handling |
| `body_filter_handler.lua` | `body_filter_handler_spec.lua`, `body_filter_handler_extended_spec.lua` | JSON parsing, token storage, chunked responses |
| `log_handler.lua` | `log_handler_spec.lua`, `log_handler_extended_spec.lua` | WebSocket tunnel detection, session cleanup |
| `session_guard.lua` | `session_guard_spec.lua`, `session_guard_extended_spec.lua` | Session expiration, token revocation |

### Key Test Scenarios

#### Access Handler
- Requests without cookies
- Invalid/missing JTI
- Expired sessions
- Valid session propagation
- Edge cases: empty values, special characters

#### Header Filter Handler
- JWT validation (signature, issuer, audience)
- Cookie creation with proper flags (Secure, HttpOnly, SameSite)
- Redirect URL rewriting (301, 302, 303, 307, 308)
- Replay attack prevention (JTI tracking)
- Username normalization

#### Body Filter Handler
- JSON response detection
- Token mapping storage
- Chunked response handling
- Unicode and special characters

#### Log Handler
- WebSocket tunnel closure detection
- Admin user filtering
- JWT vs manual session differentiation
- Pending closure flagging

#### Session Guard
- Expired session termination
- Guacamole API integration
- Token revocation
- Error handling (timeouts, malformed responses)

## Test Framework

Tests use a custom lightweight framework (`helpers/runner.lua`) with:
- `runner.describe(name, fn)` - Define test suite
- `runner.it(name, fn)` - Define test case
- `runner.assert.equals(expected, actual)` - Assert equality
- `runner.assert.truthy(value)` - Assert truthy value
- `runner.assert.contains(list, item)` - Assert list contains item

### Mock Objects

#### ngx_stub.lua
Provides a mock `ngx` object with:
- Shared dictionaries (`ngx.shared.cache`, `ngx.shared.config`)
- Request/response handling
- Time simulation
- Logging capture

#### http_client_stub.lua
Simulates HTTP client responses for testing Guacamole API calls.

## Adding New Tests

1. Create a new spec file in `tests/unit/`:
```lua
local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local module = require "modules.your_module"

runner.describe("Your module", function()
    runner.it("does something", function()
        local ngx = ngx_factory.new({ ... })
        module.run(ngx)
        runner.assert.equals(expected, ngx.some_value)
    end)
end)

return runner
```

2. Add the spec to `run.lua`:
```lua
local specs = {
    -- existing specs...
    "tests.unit.your_module_spec"
}
```

3. Run the tests to verify.

## CI/CD Integration

The tests can be integrated into CI pipelines:

```yaml
# GitHub Actions example
- name: Run Lua tests
  run: |
    docker build -t lua-tests -f openresty/Dockerfile.test openresty
    docker run --rm lua-tests luajit tests/run.lua
```
