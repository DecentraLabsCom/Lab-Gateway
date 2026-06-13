from sqlalchemy.engine import make_url

import worker


def test_build_ops_dsn_escapes_reserved_password_characters(monkeypatch):
    monkeypatch.setattr(worker, "MYSQL_DSN", None)
    monkeypatch.setattr(worker, "MYSQL_USER", "guacamole_user")
    monkeypatch.setattr(worker, "MYSQL_PASSWORD", "Gu@c_27411_33")
    monkeypatch.setattr(worker, "MYSQL_HOSTNAME", "mysql")
    monkeypatch.setattr(worker, "MYSQL_PORT", 3306)
    monkeypatch.setattr(worker, "OPS_MYSQL_DATABASE", "blockchain_services")

    url = make_url(worker.build_ops_dsn())

    assert url.host == "mysql"
    assert url.username == "guacamole_user"
    assert url.password == "Gu@c_27411_33"
    assert url.database == "blockchain_services"
