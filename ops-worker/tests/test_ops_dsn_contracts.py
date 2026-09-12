from types import SimpleNamespace

import worker


def test_build_ops_dsn_contract_prefers_explicit_shared_dsn(monkeypatch):
    monkeypatch.setattr(worker, "MYSQL_DSN", "mysql+pymysql://shared/base")
    monkeypatch.setattr(worker, "OPS_MYSQL_USER", "ignored")
    monkeypatch.setattr(worker, "OPS_MYSQL_PASSWORD", "ignored")
    monkeypatch.setattr(worker, "OPS_MYSQL_DATABASE", "ignored")

    assert worker.build_ops_dsn() == "mysql+pymysql://shared/base"


def test_build_ops_dsn_contract_uses_backend_principal(monkeypatch):
    calls = []

    def create_url(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(render_as_string=lambda hide_password: "backend-rendered")

    monkeypatch.setattr(worker, "MYSQL_DSN", None)
    monkeypatch.setattr(worker, "OPS_MYSQL_USER", "ops_backend")
    monkeypatch.setattr(worker, "OPS_MYSQL_PASSWORD", "secret")
    monkeypatch.setattr(worker, "OPS_MYSQL_DATABASE", "blockchain_services")
    monkeypatch.setattr(worker, "MYSQL_HOSTNAME", "mysql")
    monkeypatch.setattr(worker, "MYSQL_PORT", 3306)
    monkeypatch.setattr(worker, "URL", SimpleNamespace(create=create_url))

    assert worker.build_ops_dsn() == "backend-rendered"
    assert calls == [
        (
            ("mysql+pymysql",),
            {
                "username": "ops_backend",
                "password": "secret",
                "host": "mysql",
                "port": 3306,
                "database": "blockchain_services",
            },
        )
    ]


def test_build_ops_dsn_contract_returns_none_without_complete_principal(monkeypatch):
    monkeypatch.setattr(worker, "MYSQL_DSN", None)
    monkeypatch.setattr(worker, "OPS_MYSQL_USER", "ops_backend")
    monkeypatch.setattr(worker, "OPS_MYSQL_PASSWORD", "")
    monkeypatch.setattr(worker, "OPS_MYSQL_DATABASE", "blockchain_services")

    assert worker.build_ops_dsn() is None
