import base64

import jwt
import pytest

from session_observer_auth import (
    SessionObserverConfigurationError,
    create_session_observer_authorization,
)


def test_session_observer_authorization_contains_short_lived_scoped_claims():
    key = b"s" * 32
    secret = base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")

    authorization = create_session_observer_authorization("gateway-42", secret)

    assert authorization.startswith("Bearer ")
    claims = jwt.decode(
        authorization.removeprefix("Bearer "),
        key,
        algorithms=["HS256"],
        audience="session-observation",
        issuer="gateway-42",
    )
    assert claims["sub"] == "gateway-42"
    assert claims["scope"] == "session-observation:submit"
    assert 0 < claims["exp"] - claims["iat"] <= 60
    assert claims["jti"]


@pytest.mark.parametrize(
    ("gateway_id", "secret", "message"),
    [
        ("", "s" * 32, "credentials are not configured"),
        ("gateway-42", "", "credentials are not configured"),
        ("gateway-42", base64.urlsafe_b64encode(b"s" * 10).rstrip(b"=").decode("ascii"), "signing secret is too short"),
        ("gateway-42", "abcde", "Invalid session observer signing secret"),
    ],
)
def test_session_observer_authorization_rejects_invalid_configuration(gateway_id, secret, message):
    with pytest.raises(SessionObserverConfigurationError, match=message):
        create_session_observer_authorization(gateway_id, secret)
