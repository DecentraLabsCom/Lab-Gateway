import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from session_ticket_service import issue_session_ticket, redeem_session_ticket


class FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


def _dependencies(response, *, error_text="error", error_payload=None):
    calls = []

    async def post_request(url, *, payload, authorization):
        calls.append({
            "url": url,
            "payload": payload,
            "authorization": authorization,
        })
        return response

    return {
        "calls": calls,
        "post_request": post_request,
        "build_payload": lambda **kwargs: kwargs,
        "extract_error_text": lambda _response: error_text,
        "extract_error_payload": lambda _response: error_payload or {"error": error_text},
        "coerce_epoch_seconds": lambda value: int(value) if value is not None else None,
        "normalize_ticket_id": lambda value: value,
        "logger": MagicMock(),
    }


def test_issue_session_ticket_returns_ticket_and_expiry():
    dependencies = _dependencies(
        FakeResponse(json_data={"sessionTicket": "st_ticket", "expiresAt": 123}),
    )

    result = asyncio.run(issue_session_ticket(
        "Bearer caller",
        lab_id="42",
        reservation_key="RES-1",
        request_id="req-1",
        issue_url="https://auth/issue",
          **{key: value for key, value in dependencies.items()
              if key not in {"calls", "extract_error_payload"}},
    ))

    assert result == ("st_ticket", 123)
    assert dependencies["calls"] == [{
        "url": "https://auth/issue",
        "payload": {"lab_id": "42", "reservation_key": "RES-1"},
        "authorization": "Bearer caller",
    }]


def test_issue_session_ticket_maps_upstream_error():
    dependencies = _dependencies(
        FakeResponse(status_code=403, text="forbidden"),
        error_text="forbidden",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(issue_session_ticket(
            "Bearer caller",
            lab_id="42",
            reservation_key=None,
            issue_url="https://auth/issue",
                **{key: value for key, value in dependencies.items()
                    if key not in {"calls", "extract_error_payload"}},
        ))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Unable to issue session ticket: forbidden"


def test_redeem_session_ticket_returns_claims_and_uses_observer_authorization():
    dependencies = _dependencies(
        FakeResponse(json_data={"claims": {"sub": "user"}}),
    )

    result = asyncio.run(redeem_session_ticket(
        session_ticket="st_ticket",
        lab_id="42",
        reservation_key="RES-1",
        session_id="session-1",
        request_id="req-1",
        redeem_url="https://auth/redeem",
        observer_authorization=lambda: "Bearer observer",
        **{key: value for key, value in dependencies.items()
              if key not in {"calls", "extract_error_text", "coerce_epoch_seconds"}},
    ))

    assert result == {"sub": "user"}
    assert dependencies["calls"] == [{
        "url": "https://auth/redeem",
        "payload": {
            "session_ticket": "st_ticket",
            "lab_id": "42",
            "reservation_key": "RES-1",
        },
        "authorization": "Bearer observer",
    }]


def test_redeem_session_ticket_rejects_missing_claims():
    dependencies = _dependencies(FakeResponse(json_data={"claims": []}))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(redeem_session_ticket(
            session_ticket="st_ticket",
            lab_id=None,
            reservation_key=None,
            redeem_url="https://auth/redeem",
            observer_authorization=lambda: "Bearer observer",
            **{key: value for key, value in dependencies.items()
                    if key not in {"calls", "extract_error_text", "coerce_epoch_seconds"}},
        ))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INTERNAL_ERROR",
        "error": "Invalid ticket redeem response",
    }