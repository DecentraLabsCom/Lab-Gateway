from sqlalchemy.engine import make_url

import worker


def test_build_ops_dsn_escapes_reserved_password_characters(monkeypatch):
    monkeypatch.setattr(worker, "MYSQL_DSN", None)
    monkeypatch.setattr(worker, "OPS_MYSQL_USER", "ops_backend")
    monkeypatch.setattr(worker, "OPS_MYSQL_PASSWORD", "Ops@backend_42")
    monkeypatch.setattr(worker, "MYSQL_HOSTNAME", "mysql")
    monkeypatch.setattr(worker, "MYSQL_PORT", 3306)
    monkeypatch.setattr(worker, "OPS_MYSQL_DATABASE", "blockchain_services")

    dsn = worker.build_ops_dsn()
    assert dsn is not None
    url = make_url(dsn)

    assert url.host == "mysql"
    assert url.username == "ops_backend"
    assert url.password == "Ops@backend_42"
    assert url.database == "blockchain_services"


def test_build_guacamole_dsn_uses_worker_guacamole_principal(monkeypatch):
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "ops_guac")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "Ops@guac_42")
    monkeypatch.setattr(worker, "MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", "guacamole_db")

    dsn = worker.build_guacamole_dsn()
    assert dsn is not None
    url = make_url(dsn)

    assert url.username == "ops_guac"
    assert url.password == "Ops@guac_42"
    assert url.database == "guacamole_db"
