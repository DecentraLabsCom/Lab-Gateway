from datetime import datetime, timezone

from sqlalchemy import create_engine, text

import worker


def create_outbox_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE gateway_session_observation_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key VARCHAR(64) NOT NULL UNIQUE,
                reservation_key VARCHAR(80) NOT NULL,
                jwt_jti VARCHAR(128) NOT NULL,
                session_id VARCHAR(128) NOT NULL,
                gateway_id VARCHAR(128) NOT NULL,
                access_type VARCHAR(32) NOT NULL,
                observed_at DATETIME NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                locked_at DATETIME NULL,
                delivered_at DATETIME NULL,
                last_error VARCHAR(1024) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    return engine


def insert_pending(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO gateway_session_observation_outbox (
                dedup_key, reservation_key, jwt_jti, session_id, gateway_id,
                access_type, observed_at, status, attempts, next_attempt_at
            ) VALUES (
                'a' || '0', '0xreservation', 'jwt-jti', 'guac:session-hash',
                'gateway-a', 'guacamole', :observed_at, 'PENDING', 0, CURRENT_TIMESTAMP
            )
        """), {"observed_at": datetime(2026, 1, 1, tzinfo=timezone.utc)})


def test_delivers_observation_and_marks_it_sent(monkeypatch):
    engine = create_outbox_engine()
    insert_pending(engine)
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "ACCESS_AUDIT_TOKEN", "internal-token")
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_OUTBOX_ENABLED", True)
    captured = {}

    class Response:
        status_code = 200
        content = b'{"recorded":true}'

        @staticmethod
        def json():
            return {"recorded": True}

    def post(url, json, headers, timeout):
        captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return Response()

    monkeypatch.setattr(worker.requests, "post", post)

    assert worker.deliver_session_observation_outbox() == 1
    assert captured["json"]["observedAt"] == 1767225600
    assert captured["headers"][worker.ACCESS_AUDIT_TOKEN_HEADER] == "internal-token"
    with engine.begin() as conn:
        status = conn.execute(text("SELECT status FROM gateway_session_observation_outbox")).scalar_one()
    assert status == "SENT"


def test_retries_when_backend_does_not_confirm_the_observation(monkeypatch):
    engine = create_outbox_engine()
    insert_pending(engine)
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "ACCESS_AUDIT_TOKEN", "internal-token")
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_OUTBOX_ENABLED", True)

    class Response:
        status_code = 200
        content = b'{"recorded":false}'

        @staticmethod
        def json():
            return {"recorded": False}

    monkeypatch.setattr(worker.requests, "post", lambda *_, **__: Response())

    assert worker.deliver_session_observation_outbox() == 0
    with engine.begin() as conn:
        row = conn.execute(text("SELECT status, attempts, last_error FROM gateway_session_observation_outbox")).mappings().one()
    assert row["status"] == "RETRY"
    assert row["attempts"] == 1
    assert "recorded=False" in row["last_error"]


def test_ingest_requires_the_gateway_specific_token_and_is_idempotent(monkeypatch):
    engine = create_outbox_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    client = worker.APP.test_client()
    payload = {
        "dedupKey": "b" * 64,
        "reservationKey": "0xreservation",
        "jwtJti": "jwt-jti",
        "sessionId": "guac:session-hash",
        "gatewayId": "gateway-a",
        "accessType": "guacamole",
        "observedAt": 1767225600,
    }

    unauthorized = client.post("/internal/session-observations", json=payload)
    accepted = client.post(
        "/internal/session-observations",
        json=payload,
        headers={"X-Gateway-Observation-Token": "gateway-token"},
    )
    duplicate = client.post(
        "/internal/session-observations",
        json=payload,
        headers={"X-Gateway-Observation-Token": "gateway-token"},
    )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 202
    assert duplicate.status_code == 202
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM gateway_session_observation_outbox")).scalar_one()
    assert count == 1


def test_does_not_deliver_lite_gateway_observations_without_the_issuer_audit_url(monkeypatch):
    engine = create_outbox_engine()
    insert_pending(engine)
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "ACCESS_AUDIT_TOKEN", "internal-token")
    monkeypatch.setattr(worker, "ACCESS_AUDIT_URL", "")
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_OUTBOX_ENABLED", True)

    assert worker.deliver_session_observation_outbox() == 0
    with engine.begin() as conn:
        status = conn.execute(text("SELECT status FROM gateway_session_observation_outbox")).scalar_one()
    assert status == "PENDING"
