"""
JWT verification for FMU Runner.

In Full Gateway mode, booking JWTs are validated against the local
blockchain-services JWKS endpoint.

In Lite Gateway mode, the gateway trusts JWTs issued by an external Full
Gateway configured through ISSUER. FMU validation must therefore use that
issuer and its JWKS endpoint instead of the local blockchain-services one.
"""

import os
import logging
import time
import hashlib
from typing import Optional
from urllib.parse import urlparse

import jwt
import httpx
from fastapi import HTTPException, Request

logger = logging.getLogger("fmu-runner.auth")

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}


def _is_loopback_or_private_host(host: str) -> bool:
    """Return True for loopback or RFC1918/reserved hosts (port stripped)."""
    host_only = host.split(":")[0].lower()
    if host_only in _LOOPBACK_HOSTS or host_only.startswith("127."):
        return True
    parts = host_only.split(".")
    if len(parts) == 4:
        try:
            first, second = int(parts[0]), int(parts[1])
            if first == 10:
                return True
            if first == 172 and 16 <= second <= 31:
                return True
            if first == 192 and second == 168:
                return True
        except ValueError:
            # Non-numeric host labels are not private IPv4 addresses.
            pass
    return False

def _normalize_issuer(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def _build_local_issuer() -> str:
    """Build the same Full-mode issuer used by OpenResty's TLS bootstrap."""
    server_name = (os.getenv("SERVER_NAME") or "localhost").strip() or "localhost"
    https_port = (os.getenv("HTTPS_PORT") or "443").strip() or "443"
    port_suffix = "" if https_port == "443" else f":{https_port}"
    return f"https://{server_name}{port_suffix}/auth"


def _build_jwks_url_from_issuer(issuer: str) -> str:
    """Derive the JWKS URL from an issuer string.

    The JWKS endpoint is always at <issuer>/jwks, preserving any path prefix so
    non-root issuers (e.g. https://host/tenants/acme/auth) resolve correctly.
    HTTPS is required for non-loopback/private hosts to prevent key substitution
    attacks when fetching signing public keys over an untrusted network.
    """
    parsed = urlparse(issuer)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid issuer URL: {issuer}")
    if parsed.scheme != "https" and not _is_loopback_or_private_host(parsed.netloc):
        raise ValueError(
            f"Insecure issuer scheme '{parsed.scheme}': JWKS public keys must be "
            f"fetched over HTTPS for non-loopback hosts. Got: {issuer}"
        )
    # Use issuer as the base so any path prefix is preserved (#2).
    return issuer.rstrip("/") + "/jwks"


def _resolve_auth_jwks_url() -> str:
    explicit = os.getenv("AUTH_JWKS_URL")
    if explicit and explicit.strip():
        return explicit.strip()

    issuer = _normalize_issuer(os.getenv("ISSUER"))
    if issuer:
        return _build_jwks_url_from_issuer(issuer)

    return "http://blockchain-services:8080/auth/jwks"


def _resolve_jwt_issuer() -> Optional[str]:
    explicit = _normalize_issuer(os.getenv("JWT_ISSUER"))
    if explicit:
        return explicit
    return _normalize_issuer(os.getenv("ISSUER")) or _build_local_issuer()


AUTH_JWKS_URL = _resolve_auth_jwks_url()
JWT_ALGORITHMS = ["RS256", "ES256"]
JWT_ISSUER = _resolve_jwt_issuer()
JWT_AUDIENCE = _normalize_issuer(os.getenv("JWT_AUDIENCE"))
JWKS_CACHE_TTL = int(os.getenv("JWKS_CACHE_TTL", "300"))  # seconds

_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0.0


async def _fetch_jwks(*, force: bool = False) -> dict:
    """Fetch JWKS (cached with TTL, or immediately when a new kid appears)."""
    global _jwks_cache, _jwks_cache_time
    if not force and _jwks_cache is not None and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(AUTH_JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_cache_time = time.time()
            logger.info("Fetched JWKS from %s (%d keys)", AUTH_JWKS_URL, len(_jwks_cache.get("keys", [])))
            return _jwks_cache
    except Exception as exc:
        logger.error("Failed to fetch JWKS from %s: %s", AUTH_JWKS_URL, exc)
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc


def _extract_token(request: Request) -> str:
    """Extract the FMU credential from the explicit Bearer header only.

    Query-string and cookie JWTs are deliberately not accepted: both can leak
    through browser history, access logs, referrers, and ambient same-origin
    requests.  Browser runtimes use an opaque session ticket for WebSockets.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header[7:].strip():
        return auth_header[7:].strip()
    raise HTTPException(status_code=401, detail="Missing authentication token")


async def verify_jwt_token(token: str) -> dict:
    """Verify a JWT and return decoded claims."""
    if not JWT_AUDIENCE:
        raise HTTPException(status_code=503, detail="JWT audience validation is not configured")
    jwks_data = await _fetch_jwks()

    try:
        # Build signing keys from JWKS
        jwk_client_keys = jwt.PyJWKSet.from_dict(jwks_data)
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        # Find matching key
        signing_key = None
        for key in jwk_client_keys.keys:
            if kid and key.key_id == kid:
                signing_key = key
                break

        if signing_key is None:
            # A signing-key rotation can legitimately happen before the
            # normal cache TTL.  Refresh once so both current and overlap JWKS
            # entries are observed without making every request uncached.
            jwks_data = await _fetch_jwks(force=True)
            jwk_client_keys = jwt.PyJWKSet.from_dict(jwks_data)
            for key in jwk_client_keys.keys:
                if kid and key.key_id == kid:
                    signing_key = key
                    break
            if signing_key is None:
                raise HTTPException(status_code=401, detail="No matching signing key found")

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=JWT_ALGORITHMS,
            options={
                "verify_aud": True,
                "require": ["exp", "iat", "iss"],
            },
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
        claims["_credentialHash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return claims

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token")


async def verify_jwt(request: Request) -> dict:
    """FastAPI dependency — verify JWT and return decoded claims."""
    token = _extract_token(request)
    return await verify_jwt_token(token)
