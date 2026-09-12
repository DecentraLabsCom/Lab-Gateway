from types import SimpleNamespace

import worker


def test_build_guacamole_dsn_contract_prefers_explicit_guacamole_dsn(monkeypatch):
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", "mysql+pymysql://dedicated/db")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "ignored")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "ignored")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", "ignored")
    monkeypatch.setattr(worker, "MYSQL_DSN", "mysql+pymysql://fallback/base")

    assert worker.build_guacamole_dsn() == "mysql+pymysql://dedicated/db"


def test_build_guacamole_dsn_contract_uses_dedicated_principal(monkeypatch):
    calls = []

    def create_url(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(render_as_string=lambda hide_password: "dedicated-rendered")

    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "ops_guac")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "secret")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", "guacamole_db")
    monkeypatch.setattr(worker, "MYSQL_HOSTNAME", "mysql")
    monkeypatch.setattr(worker, "MYSQL_PORT", 3306)
    monkeypatch.setattr(worker, "URL", SimpleNamespace(create=create_url))

    assert worker.build_guacamole_dsn() == "dedicated-rendered"
    assert calls == [
        (
            ("mysql+pymysql",),
            {
                "username": "ops_guac",
                "password": "secret",
                "host": "mysql",
                "port": 3306,
                "database": "guacamole_db",
            },
        )
    ]


def test_build_guacamole_dsn_contract_derives_database_from_shared_dsn(monkeypatch):
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", "guacamole_db")
    monkeypatch.setattr(worker, "MYSQL_DSN", "mysql+pymysql://ops:secret@mysql:3306/shared")

    assert worker.build_guacamole_dsn() == "mysql+pymysql://ops:***@mysql:3306/guacamole_db"


def test_build_guacamole_dsn_contract_returns_none_without_shared_database(monkeypatch):
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", None)
    monkeypatch.setattr(worker, "MYSQL_DSN", "mysql+pymysql://ops:secret@mysql/shared")

    assert worker.build_guacamole_dsn() is None


def test_build_guacamole_dsn_contract_logs_and_closes_invalid_shared_dsn(monkeypatch):
    calls = []
    failure = ValueError("invalid DSN")

    class FakeLogger:
        def warning(self, *args):
            calls.append(args)

    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DSN", None)
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_USER", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_PASSWORD", "")
    monkeypatch.setattr(worker, "GUACAMOLE_MYSQL_DATABASE", "guacamole_db")
    monkeypatch.setattr(worker, "MYSQL_DSN", "invalid")
    monkeypatch.setattr(worker, "make_url", lambda _value: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(worker, "logging", FakeLogger())

    assert worker.build_guacamole_dsn() is None
    assert calls == [("Unable to derive Guacamole DSN from MYSQL_DSN: %s", failure)]
