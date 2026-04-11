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
            pass
    return False

def _normalize_issuer(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


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
    return _normalize_issuer(os.getenv("ISSUER"))


AUTH_JWKS_URL = _resolve_auth_jwks_url()
JWT_ALGORITHMS = ["RS256", "ES256"]
JWT_ISSUER = _resolve_jwt_issuer()  # Optional issuer check
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", None)  # Optional audience check — set to gateway URL
JWKS_CACHE_TTL = int(os.getenv("JWKS_CACHE_TTL", "300"))  # seconds

_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0.0


async def _fetch_jwks() -> dict:
    """Fetch JWKS from Blockchain-Services (cached with TTL)."""
    global _jwks_cache, _jwks_cache_time
    if _jwks_cache is not None and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
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
    """Extract Bearer token from Authorization header or cookie.

    Resolution order (first match wins):
      1. ``Authorization: Bearer <token>`` header — **preferred, used in production**.
         The Marketplace proxy forwards this header after obtaining a JWT via
         the SSO or wallet-signing flow in ``labAuth.js``.
      2. Cookie fallback — only for backward-compatible / legacy browser clients
         that set the token as a cookie.  Checked names:
           - ``token``  — default name used by the Marketplace session layer
           - ``jwt``    — alternative set by some SSO providers
           - ``jti``    — legacy Blockchain-Services cookie (lowercase)
           - ``JTI``    — legacy Blockchain-Services cookie (uppercase)
         In a standard deployment only ``token`` is expected; the others are
         kept for transition periods or third-party integrations.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Fallback: cookie-based token for legacy / same-origin clients.
    # In production the Bearer header path above is the standard mechanism.
    for cookie_name in ("token", "jwt", "jti", "JTI"):
        token = request.cookies.get(cookie_name)
        if token:
            logger.debug("Using token from cookie '%s' (legacy fallback)", cookie_name)
            return token
    raise HTTPException(status_code=401, detail="Missing authentication token")


async def verify_jwt_token(token: str) -> dict:
    """Verify a JWT and return decoded claims."""
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
            raise HTTPException(status_code=401, detail="No matching signing key found")

        decode_options = {}
        if JWT_ISSUER:
            decode_options["issuer"] = JWT_ISSUER

        verify_options = {"verify_aud": False}
        decode_kwargs = {}
        if JWT_AUDIENCE:
            verify_options["verify_aud"] = True
            decode_kwargs["audience"] = JWT_AUDIENCE

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=JWT_ALGORITHMS,
            options=verify_options,
            **decode_options,
            **decode_kwargs,
        )
        return claims

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


async def verify_jwt(request: Request) -> dict:
    """FastAPI dependency — verify JWT and return decoded claims."""
    token = _extract_token(request)
    return await verify_jwt_token(token)
