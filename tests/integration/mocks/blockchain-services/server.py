#!/usr/bin/env python3
"""
Mock blockchain-services for integration testing.
Simulates auth endpoints with rate limiting.
"""
import json
import os
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# Rate limiting config
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "30"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "10"))

# Token bucket per IP
rate_limit_buckets = defaultdict(lambda: {
    "tokens": RATE_LIMIT_BURST,
    "last_refill": time.time()
})


def check_rate_limit(client_ip: str) -> bool:
    """Token bucket rate limiting."""
    if not RATE_LIMIT_ENABLED:
        return True
    
    bucket = rate_limit_buckets[client_ip]
    now = time.time()
    
    # Refill tokens based on elapsed time
    elapsed = now - bucket["last_refill"]
    tokens_to_add = elapsed * (RATE_LIMIT_REQUESTS_PER_MINUTE / 60)
    bucket["tokens"] = min(RATE_LIMIT_BURST, bucket["tokens"] + tokens_to_add)
    bucket["last_refill"] = now
    
    # Try to consume a token
    if bucket["tokens"] >= 1:
        bucket["tokens"] -= 1
        return True
    return False


def json_response(handler, status, payload, headers=None):
    """Send JSON response."""
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


# Mock JWKS response
MOCK_JWKS = {
    "keys": [{
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": "nYtfJwYyCsjZgUd9i6pN0qsjd_7LtG3jB19gOO51JbPEAXyptmHzRYKnL9zHcAcVwBMS-YmJZO802UnZXbtaYu6cGSAgRvRJUSyQQ2aBQlQzYCV_30zlGjbyWmMhBF8o0CSxkh3mp3LbIxc-5oxPDRXJ39CiX9n27RxgcueAVDGpZcxvD1pl2qad0khmjPGz18qFmvOHtZGeXz7PqasHHrksyesU_bJsDq4sRiDNa-lRZAoEr0a4GcS7pLxvszP9RPiFs49AP_e8NZ9t-LIEDh2mjznY8S0WZjzVC4sOLTYPN1sOTgahXpZFbwr3iUJsnrju-IB7FnYr1CwFCpLbGw",
        "e": "AQAB",
        "kid": "test-key-id-12345"
    }]
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence default logging
        pass

    def get_client_ip(self):
        """Get client IP from headers or connection."""
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = self.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        return self.client_address[0]

    def check_rate_limit_and_respond(self):
        """Check rate limit and send 429 if exceeded."""
        client_ip = self.get_client_ip()
        if not check_rate_limit(client_ip):
            json_response(self, 429, {
                "error": "Too many requests. Please try again later."
            }, {"Retry-After": "60"})
            return False
        return True

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "1728000")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        
        # Health check
        if parsed.path == "/health":
            json_response(self, 200, {"status": "ok", "service": "blockchain-services"})
            return
        
        # JWKS endpoint
        if parsed.path == "/auth/jwks":
            if not self.check_rate_limit_and_respond():
                return
            json_response(self, 200, MOCK_JWKS)
            return
        
        # OpenID Configuration
        if parsed.path == "/.well-known/openid-configuration":
            if not self.check_rate_limit_and_respond():
                return
            json_response(self, 200, {
                "issuer": "https://localhost:18444/auth",
                "authorization_endpoint": "https://localhost:18444/auth/wallet-auth2",
                "jwks_uri": "https://localhost:18444/auth/jwks"
            })
            return
        
        # Get message endpoint
        if parsed.path == "/auth/message":
            if not self.check_rate_limit_and_respond():
                return
            timestamp = int(time.time() * 1000)
            json_response(self, 200, {
                "message": f"Login request: {timestamp}",
                "timestamp": str(timestamp)
            })
            return
        
        # Wallet dashboard (static)
        if parsed.path.startswith("/wallet-dashboard"):
            body = b"<html><body>Mock Wallet Dashboard</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        
        json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        
        # Wallet auth endpoints
        if parsed.path in ["/auth/wallet-auth", "/auth/wallet-auth2"]:
            if not self.check_rate_limit_and_respond():
                return
            # Mock successful auth response
            json_response(self, 200, {
                "success": True,
                "token": "mock-jwt-token-for-testing",
                "labUrl": "https://localhost:18444/guacamole/"
            })
            return
        
        # SAML auth endpoints
        if parsed.path in ["/auth/saml-auth", "/auth/saml-auth2"]:
            if not self.check_rate_limit_and_respond():
                return
            json_response(self, 200, {
                "success": True,
                "token": "mock-saml-jwt-token",
                "labUrl": "https://localhost:18444/guacamole/"
            })
            return
        
        json_response(self, 404, {"error": "not found"})


def main():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Mock blockchain-services listening on port {port}")
    print(f"Rate limiting: {'enabled' if RATE_LIMIT_ENABLED else 'disabled'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
