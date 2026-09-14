from flask import Flask

import worker
from health_blueprint import create_health_blueprint


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, _statement):
        self.calls += 1
        return _ScalarResult(0)


class _Engine:
    def connect(self):
        return _Connection()


def test_health_blueprint_registers_public_route_with_explicit_providers():
    app = Flask("health-blueprint-contract")
    calls = []
    engine = _Engine()

    app.register_blueprint(
        create_health_blueprint(
            get_db_engine=lambda: calls.append("db") or engine,
            get_guacamole_db_engine=lambda: calls.append("guac") or engine,
            database_is_usable=lambda _engine, _statement: True,
            fernet_key_is_usable=lambda: calls.append("fernet") or True,
            demo_readiness=lambda: calls.append("demo") or {"status": "disabled"},
            get_hosts_loaded=lambda: calls.append("hosts") or 2,
            build_health_response=lambda **kwargs: ({
                "status": "ok",
                "hosts_loaded": kwargs["hosts_loaded"],
                "db": kwargs["db_ok"],
                "guacamole_schema": kwargs["guacamole_schema_ok"],
                "ops_secrets_key": kwargs["fernet_ok"],
                "guacamole_failed_revocations": kwargs["failed_revocations"],
                "session_observation_failed": kwargs["failed_observations"],
                "demo": kwargs["demo"],
            }, 200),
            sql_text=lambda statement: statement,
            log_warning=lambda *_args: calls.append("warning"),
        )
    )

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/health"]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "health.api_health"

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "hosts_loaded": 2,
        "db": True,
        "guacamole_schema": True,
        "ops_secrets_key": True,
        "guacamole_failed_revocations": 0,
        "session_observation_failed": 0,
        "demo": {"status": "disabled"},
    }
    assert calls == ["db", "fernet", "guac", "demo", "hosts"]


def test_worker_health_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/health"]

    assert len(rules) == 1
    assert rules[0].endpoint == "health.api_health"
