from sqlalchemy import create_engine, text

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
