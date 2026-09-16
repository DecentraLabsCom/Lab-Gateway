import asyncio
from threading import Lock
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from session_observation_service import (
    confirm_session_started,
    confirm_session_started_with_retries,
    record_browser_session_started,
)


class FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


def _dependencies(response, *, error_payload=None):
    calls = []

    async def post_observation(url, *, headers, json):
        calls.append({"url": url, "headers": headers, "json": json})
        return response

    return {
        "calls": calls,
        "post_observation": post_observation,
        "build_payload": lambda **kwargs: kwargs,
        "observer_authorization": lambda: "Bearer observer",
        "extract_error_payload": lambda _response: error_payload or {"error": "upstream"},
        "observed_at": lambda: 123,
        "normalize_ticket_id": lambda value: value,
        "logger": MagicMock(),
    }


def test_confirm_session_started_posts_observation_and_returns_true():
    dependencies = _dependencies(FakeResponse(json_data={"recorded": True}))

    result = asyncio.run(confirm_session_started(
        session_ticket="st_ticket",
        claims={"reservationKey": "RES-1"},
        session_id="session-1",
        audit_url="https://audit/session-observed",
        **{key: value for key, value in dependencies.items() if key != "calls"},
    ))

    assert result is True
    assert dependencies["calls"] == [{
        "url": "https://audit/session-observed",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer observer",
        },
        "json": {
            "session_ticket": "st_ticket",
            "reservation_key": "RES-1",
            "session_id": "session-1",
            "observed_at": 123,
        },
    }]


def test_confirm_session_started_rejects_reservation_mismatch_before_post():
    dependencies = _dependencies(FakeResponse(json_data={"recorded": True}))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(confirm_session_started(
            session_ticket="st_ticket",
            claims={"reservationKey": "RES-1"},
            reservation_key="RES-2",
            session_id="session-1",
            audit_url="https://audit/session-observed",
            **{key: value for key, value in dependencies.items() if key != "calls"},
        ))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Redeemed FMU ticket reservation mismatch"
    assert dependencies["calls"] == []


def test_confirm_session_started_fails_when_audit_is_not_configured():
    dependencies = _dependencies(FakeResponse(json_data={"recorded": True}))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(confirm_session_started(
            session_ticket="st_ticket",
            claims={"reservationKey": "RES-1"},
            session_id="session-1",
            audit_url="",
            **{key: value for key, value in dependencies.items() if key != "calls"},
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "SESSION_OBSERVATION_UNAVAILABLE",
        "error": "ACCESS_AUDIT_URL is not configured",
    }


def test_confirm_session_started_preserves_upstream_error_payload():
    dependencies = _dependencies(
        FakeResponse(status_code=409, json_data={"code": "DUPLICATE", "error": "already recorded"}),
        error_payload={"code": "DUPLICATE", "error": "already recorded"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(confirm_session_started(
            session_ticket="st_ticket",
            claims={"reservationKey": "RES-1"},
            session_id="session-1",
            audit_url="https://audit/session-observed",
            **{key: value for key, value in dependencies.items() if key != "calls"},
        ))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "DUPLICATE", "error": "already recorded"}


def test_confirm_session_started_rejects_unrecorded_response():
    dependencies = _dependencies(FakeResponse(json_data={
        "recorded": False,
        "auditRecorded": True,
        "attestationRecorded": False,
    }))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(confirm_session_started(
            session_ticket="st_ticket",
            claims={"reservationKey": "RES-1"},
            session_id="session-1",
            audit_url="https://audit/session-observed",
            **{key: value for key, value in dependencies.items() if key != "calls"},
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "SESSION_OBSERVATION_FAILED",
        "error": "Session observation was not durably recorded",
        "auditRecorded": True,
        "attestationRecorded": False,
    }


def test_confirm_session_started_with_retries_retries_server_error():
    confirm = AsyncMock(side_effect=[HTTPException(status_code=503), True])
    sleep = AsyncMock()

    result = asyncio.run(confirm_session_started_with_retries(
        confirm_session=confirm,
        session_ticket="st_ticket",
        claims={"reservationKey": "RES-1"},
        reservation_key="RES-1",
        session_id="session-1",
        max_attempts=3,
        sleep=sleep,
    ))

    assert result is True
    assert confirm.await_count == 2
    sleep.assert_awaited_once_with(0.2)


def test_confirm_session_started_with_retries_does_not_retry_client_error():
    confirm = AsyncMock(side_effect=HTTPException(status_code=400))
    sleep = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(confirm_session_started_with_retries(
            confirm_session=confirm,
            session_ticket="st_ticket",
            claims={"reservationKey": "RES-1"},
            reservation_key="RES-1",
            session_id="session-1",
            max_attempts=3,
            sleep=sleep,
        ))

    assert exc_info.value.status_code == 400
    sleep.assert_not_awaited()


def test_confirm_session_started_with_retries_retries_transport_error():
    confirm = AsyncMock(side_effect=[httpx.ConnectError("temporary"), True])
    sleep = AsyncMock()

    result = asyncio.run(confirm_session_started_with_retries(
        confirm_session=confirm,
        session_ticket="st_ticket",
        claims={"reservationKey": "RES-1"},
        reservation_key="RES-1",
        session_id="session-1",
        max_attempts=2,
        sleep=sleep,
    ))

    assert result is True
    assert confirm.await_count == 2
    sleep.assert_awaited_once_with(0.2)


def _record_dependencies(*, claims, authorization="Bearer caller"):
    observed_credentials = set()
    issue = AsyncMock(return_value=("st_ticket", 123))
    redeem = AsyncMock(return_value=claims)
    confirm_with_retries = AsyncMock(return_value=True)
    confirm = AsyncMock(return_value=True)
    return {
        "observed_credentials": observed_credentials,
        "observation_lock": Lock(),
        "extract_authorization": lambda _request: authorization,
        "issue_session_ticket": issue,
        "redeem_session_ticket": redeem,
        "retry_confirmation": confirm_with_retries,
        "confirm_session": confirm,
        "max_attempts": 3,
        "sleep": AsyncMock(),
        "issue": issue,
        "redeem": redeem,
        "confirm_with_retries": confirm_with_retries,
    }


def test_record_browser_session_started_caches_only_after_observation():
    claims = {
        "labId": "42",
        "reservationKey": "0xreservation",
        "pucHash": "puc-user",
    }
    dependencies = _record_dependencies(claims=claims)

    result = asyncio.run(record_browser_session_started(
        object(),
        claims,
        "sim-1",
        **{key: value for key, value in dependencies.items()
           if key not in {"issue", "redeem", "confirm_with_retries"}},
    ))

    assert result is True
    assert dependencies["observed_credentials"] == {"0xreservation:puc-user"}
    dependencies["issue"].assert_awaited_once_with(
        "Bearer caller",
        lab_id="42",
        reservation_key="0xreservation",
        request_id="browser_sim-1",
    )
    dependencies["redeem"].assert_awaited_once_with(
        session_ticket="st_ticket",
        lab_id="42",
        reservation_key="0xreservation",
        session_id="fmu:sim-1",
        request_id="browser_sim-1",
    )
    dependencies["confirm_with_retries"].assert_awaited_once()


def test_record_browser_session_started_skips_cached_credential():
    claims = {
        "labId": "42",
        "reservationKey": "0xreservation",
        "pucHash": "puc-user",
    }
    dependencies = _record_dependencies(claims=claims)
    dependencies["observed_credentials"].add("0xreservation:puc-user")

    result = asyncio.run(record_browser_session_started(
        object(),
        claims,
        "sim-1",
        **{key: value for key, value in dependencies.items()
           if key not in {"issue", "redeem", "confirm_with_retries"}},
    ))

    assert result is False
    dependencies["issue"].assert_not_awaited()
    dependencies["redeem"].assert_not_awaited()


def test_record_browser_session_started_requires_identity_and_authorization():
    missing_identity = _record_dependencies(claims={"labId": "42"})
    with pytest.raises(HTTPException) as identity_error:
        asyncio.run(record_browser_session_started(
            object(),
            {"labId": "42"},
            "sim-1",
            **{key: value for key, value in missing_identity.items()
               if key not in {"issue", "redeem", "confirm_with_retries"}},
        ))
    assert identity_error.value.status_code == 403

    missing_authorization = _record_dependencies(
        claims={"labId": "42", "reservationKey": "RES-1", "pucHash": "puc-user"},
        authorization="",
    )
    with pytest.raises(HTTPException) as authorization_error:
        asyncio.run(record_browser_session_started(
            object(),
            {"labId": "42", "reservationKey": "RES-1", "pucHash": "puc-user"},
            "sim-1",
            **{key: value for key, value in missing_authorization.items()
               if key not in {"issue", "redeem", "confirm_with_retries"}},
        ))
    assert authorization_error.value.status_code == 401


def test_record_browser_session_started_does_not_cache_failed_observation():
    claims = {
        "labId": "42",
        "reservationKey": "0xreservation",
        "pucHash": "puc-user",
    }
    dependencies = _record_dependencies(claims=claims)
    dependencies["confirm_with_retries"].side_effect = HTTPException(status_code=503)

    with pytest.raises(HTTPException):
        asyncio.run(record_browser_session_started(
            object(),
            claims,
            "sim-1",
            **{key: value for key, value in dependencies.items()
               if key not in {"issue", "redeem", "confirm_with_retries"}},
        ))

    assert dependencies["observed_credentials"] == set()
