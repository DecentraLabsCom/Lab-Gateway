from datetime import datetime, timezone

from sqlalchemy import create_engine, text
import pytest

import worker


def create_engine_with_guacamole_schema():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_entity (entity_id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE guacamole_user (entity_id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE guacamole_connection (connection_id INTEGER PRIMARY KEY)"))
        conn.execute(text("""
            CREATE TABLE guacamole_connection_permission (
                entity_id INTEGER NOT NULL,
                connection_id INTEGER NOT NULL
            )
        """))
    return engine


@pytest.fixture(autouse=True)
def valid_fernet_key(monkeypatch):
    monkeypatch.setattr(worker, "_load_fernet", object)


def test_health_confirms_the_guacamole_schema(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))
    guacamole_engine = create_engine_with_guacamole_schema()
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", guacamole_engine)

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["db"] is True
    assert response.json["guacamole_schema"] is True
    assert response.json["guacamole_failed_revocations"] == 0
    assert response.json["session_observation_failed"] == 0


def test_health_degrades_for_terminal_revocation_failures(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO guacamole_token_revocation_queue (status) VALUES ('FAILED')"))
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", create_engine_with_guacamole_schema())

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 503
    assert response.json["guacamole_failed_revocations"] == 1


def test_health_degrades_for_terminal_observation_failures(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO gateway_session_observation_outbox (status) VALUES ('FAILED')"))
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", create_engine_with_guacamole_schema())

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 503
    assert response.json["session_observation_failed"] == 1
    assert response.json["session_observation_outbox"] is False


def test_health_fails_when_the_guacamole_schema_is_unusable(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    empty_guacamole_engine = create_engine("sqlite:///:memory:", future=True)
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", empty_guacamole_engine)

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 503
    assert response.json["status"] == "degraded"
    assert response.json["db"] is True
    assert response.json["guacamole_schema"] is False


def test_health_degrades_when_the_ops_secrets_key_is_invalid(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", create_engine_with_guacamole_schema())

    def invalid_key():
        raise ValueError("invalid Fernet key")

    monkeypatch.setattr(worker, "_load_fernet", invalid_key)

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 503
    assert response.json["ops_secrets_key"] is False


def test_health_reports_demo_readiness_when_binding_and_station_are_ready(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))

    guacamole_engine = create_engine("sqlite:///:memory:", future=True)
    with guacamole_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_entity (entity_id INTEGER PRIMARY KEY, name VARCHAR(128), type VARCHAR(16))"))
        conn.execute(text("CREATE TABLE guacamole_user (entity_id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE guacamole_connection (connection_id INTEGER PRIMARY KEY)"))
        conn.execute(text("""
            CREATE TABLE guacamole_connection_permission (
                entity_id INTEGER NOT NULL,
                connection_id INTEGER NOT NULL,
                permission VARCHAR(32) NOT NULL
            )
        """))
        conn.execute(text("INSERT INTO guacamole_entity(entity_id, name, type) VALUES (7, 'demo', 'USER')"))
        conn.execute(text("INSERT INTO guacamole_user(entity_id) VALUES (7)"))
        conn.execute(text("INSERT INTO guacamole_connection(connection_id) VALUES (42)"))
        conn.execute(text("INSERT INTO guacamole_connection_permission(entity_id, connection_id, permission) VALUES (7, 42, 'READ')"))

    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", guacamole_engine)
    monkeypatch.setattr(worker, "DEMO_LAB_ID", "42")
    monkeypatch.setattr(worker, "DEMO_CONNECTION_ID", "42")
    monkeypatch.setattr(worker, "DEMO_USER", "demo")
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [{
        "name": "demo-station",
        "address": "192.168.1.50",
        "labs": ["42"],
    }]}))
    monkeypatch.setattr(worker, "_fetch_latest_heartbeat", lambda _conn, _name: {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": True,
        "localMode": False,
        "localSession": False,
    })

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 200
    assert response.json["demo"]["status"] == "ready"
    assert response.json["demo"]["checks"] == {
        "connection": True,
        "principal": True,
        "permission": True,
        "physical_host": True,
    }


def test_health_reports_demo_misconfigured_when_connection_is_missing(monkeypatch):
    ops_engine = create_engine("sqlite:///:memory:", future=True)
    with ops_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_token_revocation_queue (status VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE TABLE gateway_session_observation_outbox (status VARCHAR(32) NOT NULL)"))
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    guacamole_engine = create_engine("sqlite:///:memory:", future=True)
    with guacamole_engine.begin() as conn:
        conn.execute(text("CREATE TABLE guacamole_entity (entity_id INTEGER PRIMARY KEY, name VARCHAR(128), type VARCHAR(16))"))
        conn.execute(text("CREATE TABLE guacamole_user (entity_id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE guacamole_connection (connection_id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE guacamole_connection_permission (entity_id INTEGER NOT NULL, connection_id INTEGER NOT NULL, permission VARCHAR(32) NOT NULL)"))
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", guacamole_engine)
    monkeypatch.setattr(worker, "DEMO_LAB_ID", "42")
    monkeypatch.setattr(worker, "DEMO_CONNECTION_ID", "999")
    monkeypatch.setattr(worker, "DEMO_USER", "demo")

    response = worker.APP.test_client().get("/health")

    assert response.json["demo"]["status"] == "misconfigured"
