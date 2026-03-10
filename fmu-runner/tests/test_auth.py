import json
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

import auth


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_cache", None)
    monkeypatch.setattr(auth, "_jwks_cache_time", 0.0)
    monkeypatch.setattr(auth, "AUTH_JWKS_URL", "https://issuer.example/auth/jwks")
    monkeypatch.setattr(auth, "JWT_ISSUER", None)
    monkeypatch.setattr(auth, "JWT_AUDIENCE", None)
    monkeypatch.setattr(auth, "JWKS_CACHE_TTL", 300)


@pytest.fixture
def signing_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-kid"

    def _issue_token(*, claims=None, headers=None):
        payload = {"sub": "user-1", "labId": "1", "exp": 4102444800}
        if claims:
            payload.update(claims)
        token_headers = {"kid": "test-kid"}
        if headers:
            token_headers.update(headers)
        return jwt.encode(payload, private_key, algorithm="RS256", headers=token_headers)

    return {
        "jwks": {"keys": [jwk]},
        "issue_token": _issue_token,
    }


def test_extract_token_prefers_bearer_header():
    request = SimpleNamespace(
        headers={"Authorization": "Bearer header-token"},
        cookies={"token": "cookie-token"},
    )

    assert auth._extract_token(request) == "header-token"


def test_extract_token_falls_back_to_legacy_cookie_names():
    request = SimpleNamespace(headers={}, cookies={"jti": "legacy-cookie-token"})

    assert auth._extract_token(request) == "legacy-cookie-token"


def test_extract_token_rejects_missing_credentials():
    request = SimpleNamespace(headers={}, cookies={})

    with pytest.raises(HTTPException) as exc:
        auth._extract_token(request)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing authentication token"


@pytest.mark.asyncio
async def test_fetch_jwks_uses_cache_until_ttl(monkeypatch):
    calls = []
    timestamps = iter([1000.0, 1001.0])
    payload = {"keys": [{"kid": "cached-key"}]}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["timeout"] == 10

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            calls.append(url)
            return _Response()

    monkeypatch.setattr(auth.httpx, "AsyncClient", _AsyncClient)
    monkeypatch.setattr(auth.time, "time", lambda: next(timestamps))

    first = await auth._fetch_jwks()
    second = await auth._fetch_jwks()

    assert first == payload
    assert second == payload
    assert calls == ["https://issuer.example/auth/jwks"]


@pytest.mark.asyncio
async def test_fetch_jwks_returns_503_when_upstream_fails(monkeypatch):
    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(auth.httpx, "AsyncClient", _AsyncClient)

    with pytest.raises(HTTPException) as exc:
        await auth._fetch_jwks()

    assert exc.value.status_code == 503
    assert exc.value.detail == "Auth service unavailable"


@pytest.mark.asyncio
async def test_verify_jwt_token_accepts_valid_rs256_token(monkeypatch, signing_material):
    async def _fake_fetch():
        return signing_material["jwks"]

    monkeypatch.setattr(auth, "_fetch_jwks", _fake_fetch)
    token = signing_material["issue_token"]()

    claims = await auth.verify_jwt_token(token)

    assert claims["sub"] == "user-1"
    assert claims["labId"] == "1"


@pytest.mark.asyncio
async def test_verify_jwt_token_enforces_issuer_and_audience(monkeypatch, signing_material):
    async def _fake_fetch():
        return signing_material["jwks"]

    monkeypatch.setattr(auth, "_fetch_jwks", _fake_fetch)
    monkeypatch.setattr(auth, "JWT_ISSUER", "https://issuer.example/auth")
    monkeypatch.setattr(auth, "JWT_AUDIENCE", "https://gateway.example/auth")

    token = signing_material["issue_token"](
        claims={
            "iss": "https://issuer.example/auth",
            "aud": "https://gateway.example/auth",
        }
    )

    claims = await auth.verify_jwt_token(token)

    assert claims["iss"] == "https://issuer.example/auth"
    assert claims["aud"] == "https://gateway.example/auth"


@pytest.mark.asyncio
async def test_verify_jwt_token_rejects_unknown_signing_key(monkeypatch, signing_material):
    async def _fake_fetch():
        return signing_material["jwks"]

    monkeypatch.setattr(auth, "_fetch_jwks", _fake_fetch)
    token = signing_material["issue_token"](headers={"kid": "missing-kid"})

    with pytest.raises(HTTPException) as exc:
        await auth.verify_jwt_token(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "No matching signing key found"


@pytest.mark.asyncio
async def test_verify_jwt_token_rejects_expired_tokens(monkeypatch, signing_material):
    async def _fake_fetch():
        return signing_material["jwks"]

    monkeypatch.setattr(auth, "_fetch_jwks", _fake_fetch)
    token = signing_material["issue_token"](claims={"exp": 1})

    with pytest.raises(HTTPException) as exc:
        await auth.verify_jwt_token(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


@pytest.mark.asyncio
async def test_verify_jwt_token_rejects_invalid_audience(monkeypatch, signing_material):
    async def _fake_fetch():
        return signing_material["jwks"]

    monkeypatch.setattr(auth, "_fetch_jwks", _fake_fetch)
    monkeypatch.setattr(auth, "JWT_AUDIENCE", "https://gateway.example/auth")
    token = signing_material["issue_token"](claims={"aud": "https://elsewhere.example/auth"})

    with pytest.raises(HTTPException) as exc:
        await auth.verify_jwt_token(token)

    assert exc.value.status_code == 401
    assert exc.value.detail.startswith("Invalid token:")


@pytest.mark.asyncio
async def test_verify_jwt_extracts_token_before_validation(monkeypatch):
    request = SimpleNamespace(headers={"Authorization": "Bearer booking-token"}, cookies={})

    async def _fake_verify(token: str):
        assert token == "booking-token"
        return {"sub": "user-1"}

    monkeypatch.setattr(auth, "verify_jwt_token", _fake_verify)

    claims = await auth.verify_jwt(request)

    assert claims == {"sub": "user-1"}
