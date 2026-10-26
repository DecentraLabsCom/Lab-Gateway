"""Create short-lived authentication for session observation requests."""

from __future__ import annotations

import base64
import os
import time

import jwt


class SessionObserverConfigurationError(ValueError):
    """Raised when the configured observer credentials cannot sign a token."""


def create_session_observer_authorization(gateway_id: str, signing_secret: str) -> str:
    if not gateway_id or not signing_secret:
        raise SessionObserverConfigurationError(
            "Session observer gateway credentials are not configured"
        )
    try:
        padding = "=" * (-len(signing_secret) % 4)
        signing_key = base64.urlsafe_b64decode(signing_secret + padding)
    except Exception as exc:
        raise SessionObserverConfigurationError(
            "Invalid session observer signing secret"
        ) from exc
    if len(signing_key) < 32:
        raise SessionObserverConfigurationError(
            "Session observer signing secret is too short"
        )

    now = int(time.time())
    token = jwt.encode(
        {
            "iss": gateway_id,
            "sub": gateway_id,
            "aud": "session-observation",
            "scope": "session-observation:submit",
            "iat": now,
            "exp": now + 60,
            "jti": base64.urlsafe_b64encode(os.urandom(18)).rstrip(b"=").decode("ascii"),
        },
        signing_key,
        algorithm="HS256",
    )
    return f"Bearer {token}"


__all__ = ["SessionObserverConfigurationError", "create_session_observer_authorization"]
