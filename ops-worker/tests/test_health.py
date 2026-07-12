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
    guacamole_engine = create_engine_with_guacamole_schema()
    monkeypatch.setattr(worker, "DB_ENGINE", ops_engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", guacamole_engine)

    response = worker.APP.test_client().get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["db"] is True
    assert response.json["guacamole_schema"] is True


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
