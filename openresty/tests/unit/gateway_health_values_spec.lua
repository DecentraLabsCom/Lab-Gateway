local runner = require "tests.helpers.runner"
local values = require "gateway_health_values"

runner.describe("gateway_health value helpers", function()
    runner.it("normalizes issuer values without changing their scheme or path", function()
        runner.assert.equals("https://issuer.example/auth", values.normalize_issuer("  https://issuer.example/auth///  "))
        runner.assert.equals("", values.normalize_issuer(nil))
    end)

    runner.it("normalizes mode values and builds local issuers from explicit values", function()
        runner.assert.equals(true, values.lite_mode_enabled(1))
        runner.assert.equals(true, values.lite_mode_enabled("1"))
        runner.assert.equals(true, values.lite_mode_enabled(true))
        runner.assert.equals(false, values.lite_mode_enabled(0))
        runner.assert.equals("https://gateway.example/auth", values.build_local_issuer(" gateway.example ", "443"))
        runner.assert.equals("https://gateway.example:8443/auth", values.build_local_issuer("gateway.example", "8443"))
        runner.assert.equals("https://localhost/auth", values.build_local_issuer(nil, nil))
    end)

    runner.it("parses issuer URLs and omits default ports from their origin", function()
        local parsed = values.parse_issuer_url(" https://issuer.example/auth ")
        runner.assert.equals("https", parsed.scheme)
        runner.assert.equals("issuer.example", parsed.host)
        runner.assert.equals(443, parsed.port)
        runner.assert.equals("https://issuer.example", values.issuer_origin(parsed))

        local custom = values.parse_issuer_url("http://issuer.example:8080/auth")
        runner.assert.equals("http://issuer.example:8080", values.issuer_origin(custom))
        runner.assert.equals(nil, values.parse_issuer_url("issuer.example/auth"))
    end)

    runner.it("canonicalizes public key PEM bodies for comparison", function()
        local first = "-----BEGIN PUBLIC KEY-----\nabc\n123\n-----END PUBLIC KEY-----"
        local second = "-----BEGIN PUBLIC KEY-----abc123-----END PUBLIC KEY-----"
        runner.assert.truthy(values.looks_like_public_key_pem(first))
        runner.assert.equals("abc123", values.canonical_public_key(first))
        runner.assert.equals(values.canonical_public_key(first), values.canonical_public_key(second))
        runner.assert.equals(nil, values.canonical_public_key("not a key"))
    end)

    runner.it("preserves reachability, blockchain and aggregate status policies", function()
        runner.assert.equals(true, values.response_is_reachable(503, { status = "degraded" }))
        runner.assert.equals(false, values.response_is_reachable(503, "unavailable"))
        runner.assert.equals(true, values.blockchain_ready({ status = 204 }))
        runner.assert.equals(false, values.blockchain_ready({ status = 500 }))
        runner.assert.equals("UP", values.overall_status({ { ok = true, reachable = true } }))
        runner.assert.equals("PARTIAL", values.overall_status({ { ok = false, reachable = true } }))
        runner.assert.equals("DOWN", values.overall_status({ { ok = false, reachable = false } }))
    end)

    runner.it("builds check payloads and certificate expiry values without OpenResty state", function()
        local payload = values.capture_result({ status = 503 }, { status = "DEGRADED" }, "raw")
        runner.assert.equals(503, payload.status)
        runner.assert.equals(false, payload.ok)
        runner.assert.equals(true, payload.reachable)
        runner.assert.equals("raw", payload.raw)
        runner.assert.equals("no response", values.capture_result(nil).error)

        local parse_http_time = function(value)
            runner.assert.equals("Jan 12 00:00:00 1970 GMT", value)
            return 86400 * 42
        end
        runner.assert.equals(42, values.certificate_days_remaining(
            "  Jan 12 00:00:00 1970 GMT  ",
            0,
            parse_http_time
        ))
        runner.assert.equals(nil, values.certificate_days_remaining("invalid", 0, nil))
    end)

    runner.it("builds status checks while preserving mode and optional-service ordering", function()
        local full = values.build_status_checks({
            lite_mode = false,
            blockchain_ok = true,
            blockchain_reachable = true,
            guac_ok = true,
            guac_reachable = true,
            guac_api_ok = true,
            guac_api_reachable = true,
            guacd_ok = true,
            ops_ok = true,
            ops_reachable = true,
            guacamole_schema_ok = true,
            mysql_ok = true,
            fmu_runner_enabled = true,
            fmu_runner_ok = false,
            fmu_runner_reachable = true,
            aas_enabled = true,
            aas_ok = true,
            aas_reachable = true
        })
        runner.assert.equals(9, #full)
        runner.assert.equals(true, full[1].ok)
        runner.assert.equals(false, full[8].ok)

        local lite = values.build_status_checks({
            lite_mode = true,
            lite_auth = { ok = false, issuer_host_dns_ok = true },
            guac_ok = true,
            guac_reachable = true,
            guac_api_ok = true,
            guac_api_reachable = true,
            guacd_ok = true,
            ops_ok = true,
            ops_reachable = true,
            guacamole_schema_ok = true,
            mysql_ok = true,
            fmu_runner_enabled = false,
            aas_enabled = false
        })
        runner.assert.equals(7, #lite)
        runner.assert.equals(false, lite[7].ok)
        runner.assert.equals(true, lite[7].reachable)
    end)

    runner.it("builds the structured health payload from already evaluated values", function()
        local result = values.build_result({
            lite_mode = false,
            gateway_status = "UP",
            demo = { status = "disabled" },
            blockchain = { status = 200 },
            blockchain_ok = true,
            blockchain_reachable = true,
            block_body = { version = "1.0.0" },
            guac = { ok = true, status = 200 },
            guac_api = { status = 200 },
            guac_api_ok = true,
            guacd_ok = true,
            guacd_err = nil,
            ops = { ok = true, status = 200 },
            ops_body = { hosts = 2, polling_enabled = true },
            guacamole_schema_ok = true,
            mysql_ok = true,
            lite_auth = nil,
            configured_issuer = "https://gateway.example/auth",
            local_issuer = "https://gateway.example/auth",
            public_key_file_present = true,
            fmu_runner_ok = false,
            fmu_runner_enabled = false,
            fmu_runner_status = nil,
            fmu_runner_body = {},
            aas = { ok = false, status = nil },
            aas_enabled = false,
            dns = { mysql = true },
            cert_days = 42,
            fullchain_present = true,
            privkey_present = true,
            static_root_ok = true,
            env_ok = { SERVER_NAME = true }
        })
        runner.assert.equals("full", result.mode)
        runner.assert.equals("UP", result.status)
        runner.assert.equals(true, result.services.blockchain.required)
        runner.assert.equals(2, result.services.ops.hosts)
        runner.assert.equals(42, result.infra.cert.days_remaining)
        runner.assert.equals("1.0.0", result.version)
    end)
end)
