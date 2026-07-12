from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
import json

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


def test_durable_spool_survives_until_encrypted_database_insert(monkeypatch, tmp_path):
    engine = create_revocation_engine()
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "_FERNET", Fernet(Fernet.generate_key()))
    monkeypatch.setattr(worker, "GUAC_REVOCATION_SPOOL_DIR", str(tmp_path))
    entry = tmp_path / "revocation.json"
    entry.write_text(json.dumps(payload(1893456000)), encoding="utf-8")

    assert worker.ingest_guacamole_revocation_spool() == 1
    assert not entry.exists()
    with engine.begin() as conn:
        ciphertext = conn.execute(text(
            "SELECT token_ciphertext FROM guacamole_token_revocation_queue"
        )).scalar_one()
    assert "guac-secret-token" not in ciphertext
    assert worker._decrypt_runtime_secret(ciphertext) == "guac-secret-token"


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
