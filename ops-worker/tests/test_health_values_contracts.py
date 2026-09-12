import worker


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self, values):
        self.values = iter(values)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, _statement):
        return _ScalarResult(next(self.values))


class _Engine:
    def __init__(self, values):
        self.values = values

    def connect(self):
        return _Connection(self.values)


class _Hosts:
    def all_hosts(self):
        return [{"name": "lab-ws-01"}, {"name": "lab-ws-02"}]


def test_health_route_contract_preserves_healthy_payload_shape(monkeypatch):
    engine = _Engine([0, 0])
    demo = {
        "status": "disabled",
        "checks": {
            "connection": False,
            "principal": False,
            "permission": False,
            "physical_host": False,
        },
    }
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", object())
    monkeypatch.setattr(worker, "database_is_usable", lambda _engine, _statement: True)
    monkeypatch.setattr(worker, "fernet_key_is_usable", lambda: True)
    monkeypatch.setattr(worker, "demo_readiness", lambda: demo)
    monkeypatch.setattr(worker, "HOSTS", _Hosts())

    with worker.APP.test_request_context("/health"):
        response, status = worker.health()

    assert status == 200
    assert response.get_json() == {
        "status": "ok",
        "hosts_loaded": 2,
        "db": True,
        "ops_secrets_key": True,
        "guacamole_schema": True,
        "guacamole_failed_revocations": 0,
        "guacamole_revocation_queue": True,
        "session_observation_failed": 0,
        "session_observation_outbox": True,
        "demo": demo,
    }


def test_health_route_contract_marks_failed_revocation_queue_degraded(monkeypatch):
    engine = _Engine([2, 0])
    monkeypatch.setattr(worker, "DB_ENGINE", engine)
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", object())
    monkeypatch.setattr(worker, "database_is_usable", lambda _engine, _statement: True)
    monkeypatch.setattr(worker, "fernet_key_is_usable", lambda: True)
    monkeypatch.setattr(worker, "demo_readiness", lambda: {"status": "disabled", "checks": {}})
    monkeypatch.setattr(worker, "HOSTS", _Hosts())

    with worker.APP.test_request_context("/health"):
        response, status = worker.health()

    assert status == 503
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["guacamole_failed_revocations"] == 2
    assert payload["guacamole_revocation_queue"] is False
    assert payload["session_observation_outbox"] is True
