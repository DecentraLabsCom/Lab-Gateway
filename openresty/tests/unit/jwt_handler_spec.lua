local runner = require "tests.helpers.runner"
local ngx_factory = require "tests.helpers.ngx_stub"
local jwt_handler = require "modules.jwt_handler"

runner.describe("JWT Handler - Authentication & Authorization", function()

    runner.describe("JWT Validation", function()
        runner.it("accepts valid JWT with correct claims", function()
            local valid_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsInB1YyI6InVybjptYWNlOnRlcmVuYS5vcmc6c2NoYWM6cGVyc29uYWxVbmlxdWVDb2RlOmludDplczp1bml2ZXJzaXR5LmVkdTpwZXJzb246MTIzNDUiLCJsYWJJZCI6ImxhYi0xMjMiLCJyZXNlcnZhdGlvbklkIjoiMTIzIiwiZXhwIjoxNzY3MzQ1NjAwLCJpYXQiOjE3NjczNDIwMDAsImlzcyI6ImRlY2VudHJhbGFicyJ9.signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. valid_jwt },
                now = 1767343000  -- Within expiration
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(true, result.valid)
            runner.assert.equals("user-123", result.claims.sub)
            runner.assert.equals("lab-123", result.claims.labId)
        end)

        runner.it("rejects expired JWT", function()
            local expired_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6MTY3MjU0ODgwMH0.expired_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. expired_jwt },
                now = 1767345600  -- After expiration
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(false, result.valid)
            runner.assert.equals("Token expired", result.error)
        end)

        runner.it("rejects JWT with invalid signature", function()
            local invalid_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6MTc2NzM0NTYwMH0.invalid_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. invalid_jwt },
                now = 1767343000
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(false, result.valid)
            runner.assert.equals("Invalid signature", result.error)
        end)

        runner.it("rejects JWT missing required claims", function()
            local incomplete_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.incomplete_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. incomplete_jwt },
                now = 1767343000
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(false, result.valid)
            runner.assert.equals("Missing required claims: puc, labId, reservationId", result.error)
        end)

        runner.it("rejects malformed JWT", function()
            local malformed_jwt = "not-a-jwt-at-all"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. malformed_jwt },
                now = 1767343000
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(false, result.valid)
            runner.assert.equals("Malformed JWT", result.error)
        end)

        runner.it("rejects JWT from wrong issuer", function()
            local wrong_issuer_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImlzcyI6Indyb25nLWlzc3VlciJ9.wrong_issuer_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. wrong_issuer_jwt },
                now = 1767343000
            })

            local result = jwt_handler.validate_jwt(ngx)
            runner.assert.equals(false, result.valid)
            runner.assert.equals("Invalid issuer", result.error)
        end)
    end)

    runner.describe("JWKS Integration", function()
        runner.it("fetches and caches JWKS from Blockchain-Services", function()
            local ngx = ngx_factory.new({
                http = {
                    get = function(url)
                        runner.assert.equals("https://blockchain-services.decentralabs.edu/auth/jwks", url)
                        return {
                            status = 200,
                            body = '{"keys":[{"kid":"key-1","n":"modulus","e":"exponent","alg":"RS256"}]}'
                        }
                    end
                }
            })

            local jwks = jwt_handler.fetch_jwks(ngx)
            runner.assert.equals("key-1", jwks.keys[1].kid)
            runner.assert.equals("RS256", jwks.keys[1].alg)
        end)

        runner.it("handles JWKS fetch failure gracefully", function()
            local ngx = ngx_factory.new({
                http = {
                    get = function(url)
                        return {
                            status = 500,
                            body = "Internal Server Error"
                        }
                    end
                }
            })

            local jwks = jwt_handler.fetch_jwks(ngx)
            runner.assert.equals(nil, jwks)
        end)

        runner.it("uses cached JWKS when available", function()
            local cache = { ["jwks"] = '{"keys":[{"kid":"cached-key","alg":"RS256"}]}' }
            local ngx = ngx_factory.new({
                cache = cache
            })

            local jwks = jwt_handler.fetch_jwks(ngx)
            runner.assert.equals("cached-key", jwks.keys[1].kid)
            -- Should not have made HTTP request
        end)
    end)

    runner.describe("Session Management", function()
        runner.it("creates Guacamole session for valid JWT", function()
            local valid_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsInB1YyI6InVybjptYWNlOnRlcmVuYS5vcmc6c2NoYWM6cGVyc29uYWxVbmlxdWVDb2RlOmludDplczp1bml2ZXJzaXR5LmVkdTpwZXJzb246MTIzNDUiLCJsYWJJZCI6ImxhYi0xMjMiLCJyZXNlcnZhdGlvbklkIjoiMTIzIn0.valid_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. valid_jwt },
                now = 1767343000
            })

            -- Mock Guacamole session creation
            ngx.http = {
                post = function(url, body)
                    runner.assert.equals("http://guacamole:8080/guacamole/api/tokens", url)
                    return {
                        status = 200,
                        body = '{"authToken":"guac-token-123","username":"user-123"}'
                    }
                end
            }

            local session = jwt_handler.create_guacamole_session(ngx)
            runner.assert.equals("guac-token-123", session.authToken)
            runner.assert.equals("user-123", session.username)
        end)

        runner.it("handles Guacamole session creation failure", function()
            local valid_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.valid_signature"

            local ngx = ngx_factory.new({
                var = { http_authorization = "Bearer " .. valid_jwt },
                now = 1767343000,
                http = {
                    post = function(url, body)
                        return {
                            status = 503,
                            body = "Guacamole service unavailable"
                        }
                    end
                }
            })

            local session = jwt_handler.create_guacamole_session(ngx)
            runner.assert.equals(nil, session)
            runner.assert.equals(ngx.HTTP_SERVICE_UNAVAILABLE, ngx.status)
        end)
    end)

    runner.describe("Rate Limiting", function()
        runner.it("allows requests within rate limit", function()
            local cache = {}
            local ngx = ngx_factory.new({
                cache = cache,
                var = { remote_addr = "192.168.1.100" },
                now = 1767343000
            })

            local allowed = jwt_handler.check_rate_limit(ngx, "192.168.1.100")
            runner.assert.equals(true, allowed)
        end)

        runner.it("blocks requests exceeding rate limit", function()
            local cache = { ["rate_limit:192.168.1.100"] = "10" }  -- Exceeded limit
            local ngx = ngx_factory.new({
                cache = cache,
                var = { remote_addr = "192.168.1.100" },
                now = 1767343000
            })

            local allowed = jwt_handler.check_rate_limit(ngx, "192.168.1.100")
            runner.assert.equals(false, allowed)
            runner.assert.equals(ngx.HTTP_TOO_MANY_REQUESTS, ngx.status)
        end)
    end)
end)