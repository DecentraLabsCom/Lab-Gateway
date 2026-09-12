import worker


def test_operations_recent_route_contract_requires_database(client, monkeypatch):
    monkeypatch.setattr(worker, "DB_ENGINE", None)

    response = client.get("/api/operations/recent")

    assert response.status_code == 500
    assert response.json == {"error": "Database not configured"}


def test_operations_recent_route_contract_rejects_unknown_host_filter(client, monkeypatch):
    monkeypatch.setattr(worker, "DB_ENGINE", object())
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.get("/api/operations/recent?host=missing")

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found"}


def test_operations_recent_route_contract_hides_storage_errors(client, monkeypatch):
    class _BrokenEngine:
        def begin(self):
            raise RuntimeError("secret database details")

    monkeypatch.setattr(worker, "DB_ENGINE", _BrokenEngine())

    response = client.get("/api/operations/recent")

    assert response.status_code == 500
    assert response.json["error"] == "Internal server error"
    assert response.json["code"] == "INTERNAL_ERROR"
    assert "secret database details" not in response.get_data(as_text=True)
