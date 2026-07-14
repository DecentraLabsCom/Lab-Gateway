from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

import worker


def create_revocation_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE guacamole_token_revocation_queue (
                token_hash VARCHAR(64) PRIMARY KEY,
                token_ciphertext TEXT NOT NULL,
                username VARCHAR(128) NOT NULL,
                reservation_key VARCHAR(80) NOT NULL,
                jwt_jti VARCHAR(128) NOT NULL,
                gateway_id VARCHAR(128) NOT NULL,
                expires_at DATETIME NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                observed_at DATETIME NULL,
                revoked_at DATETIME NULL,
                last_error VARCHAR(1024) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    return engine


def payload(expires_at=1):
    return {
        "authToken": "guac-secret-token",
        "username": "dlabs-res-user",
        "reservationKey": "0xreservation",
        "jwtJti": "jwt-jti",
        "gatewayId": "gateway-a",
        "expiresAt": expires_at,
    }


def test_ingest_encrypts_the_guacamole_token(monkeypatch):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")

    response = worker.APP.test_client().post(
        "/internal/guacamole-token-revocations",
        json=payload(1893456000),
        headers={"X-Gateway-Observation-Token": "gateway-token"},
    )

    assert response.status_code == 202
    with engine.begin() as conn:
        ciphertext = conn.execute(text(
            "SELECT token_ciphertext FROM guacamole_token_revocation_queue"
        )).scalar_one()
    assert "guac-secret-token" not in ciphertext
    assert worker._decrypt_runtime_secret(ciphertext) == "guac-secret-token"


def test_duplicate_reopens_a_terminal_revocation(monkeypatch):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    assert worker.enqueue_guacamole_token_revocation(payload(1893456000))
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE guacamole_token_revocation_queue SET status = 'FAILED', attempts = 20, last_error = 'offline'"
        ))

    assert worker.enqueue_guacamole_token_revocation(payload(1893456000))

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT status, attempts, last_error FROM guacamole_token_revocation_queue"
        )).mappings().one()
    assert row["status"] == "RETRY"
    assert row["attempts"] == 0
    assert row["last_error"] is None
def test_expired_token_is_revoked_after_restart_safe_lookup(monkeypatch):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    monkeypatch.setattr(worker, "GUAC_ADMIN_USER", "admin")
    monkeypatch.setattr(worker, "GUAC_ADMIN_PASS", "secret")
    assert worker.enqueue_guacamole_token_revocation(payload())

    class Response:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body or {}

        def json(self):
            return self._body

    monkeypatch.setattr(worker.requests, "post", lambda *_, **__: Response(
        200, {"authToken": "admin-token", "dataSource": "mysql"}
    ))
    monkeypatch.setattr(worker.requests, "get", lambda *_, **__: Response(200, {}))
    deleted = {}

    def delete(url, params, timeout):
        deleted.update({"url": url, "params": params, "timeout": timeout})
        return Response(204)

    monkeypatch.setattr(worker.requests, "delete", delete)

    assert worker.process_guacamole_token_revocations() == 1
    assert "guac-secret-token" in deleted["url"]
    with engine.begin() as conn:
        status = conn.execute(text(
            "SELECT status FROM guacamole_token_revocation_queue"
        )).scalar_one()
    assert status == "REVOKED"


def test_reconciliation_emits_session_started_only_for_an_active_guacamole_connection(monkeypatch):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    assert worker.enqueue_guacamole_token_revocation(payload(1893456000))

    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    def get(url, params, timeout):
        if url.endswith("/activeConnections"):
            return Response(200, {
                "connection-1": {"username": "dlabs-res-user"},
            })
        return Response(200, {"username": "dlabs-res-user"})

    observed = []
    monkeypatch.setattr(worker.requests, "get", get)
    monkeypatch.setattr(worker, "enqueue_session_observation", lambda value: observed.append(value) or True)

    worker._reconcile_guacamole_observations("admin-token", "mysql")

    assert len(observed) == 1
    assert observed[0]["reservationKey"] == "0xreservation"
    assert observed[0]["accessType"] == "guacamole"
    with engine.begin() as conn:
        assert conn.execute(text(
            "SELECT observed_at IS NOT NULL FROM guacamole_token_revocation_queue"
        )).scalar_one() == 1


def test_reconciliation_does_not_emit_evidence_for_a_rejected_or_inactive_tunnel(monkeypatch):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    assert worker.enqueue_guacamole_token_revocation(payload(1893456000))

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {}

    observed = []
    monkeypatch.setattr(worker.requests, "get", lambda *_, **__: Response())
    monkeypatch.setattr(worker, "enqueue_session_observation", lambda value: observed.append(value) or True)

    worker._reconcile_guacamole_observations("admin-token", "mysql")

    assert observed == []


def test_reconciliation_uses_guacamole_connection_history_for_short_sessions(monkeypatch):
    engine = create_revocation_engine()
    history_engine = create_engine("sqlite:///:memory:", future=True)
    with history_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE guacamole_connection_history (
                history_id INTEGER PRIMARY KEY,
                username VARCHAR(128) NOT NULL,
                start_date DATETIME NOT NULL,
                end_date DATETIME NULL
            )
        """))
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", history_engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    assert worker.enqueue_guacamole_token_revocation(payload(1893456000))

    with engine.begin() as conn:
        issued_at = conn.execute(text(
            "SELECT created_at FROM guacamole_token_revocation_queue"
        )).scalar_one()
    with history_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO guacamole_connection_history (history_id, username, start_date, end_date) "
            "VALUES (1, :username, :start_date, :end_date)"
        ), {
            "username": "dlabs-res-user",
            "start_date": issued_at,
            "end_date": issued_at,
        })

    with engine.begin() as conn:
        queue_row = conn.execute(text(
            "SELECT username, created_at, expires_at FROM guacamole_token_revocation_queue"
        )).mappings().one()
    assert worker._guacamole_connection_history_observed(queue_row) is True

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {}

    observed = []
    monkeypatch.setattr(worker.requests, "get", lambda *_, **__: Response())
    monkeypatch.setattr(worker, "enqueue_session_observation", lambda value: observed.append(value) or True)

    worker._reconcile_guacamole_observations("admin-token", "mysql")

    assert len(observed) == 1
    assert observed[0]["sessionId"].startswith("guac:")
