import worker


def test_hosts_reload_route_contract_returns_count_on_success(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker,
        "reload_hosts",
        lambda: calls.append("reload") or (3, None),
    )

    response = client.post("/api/hosts/reload")

    assert response.status_code == 200
    assert response.json == {"reloaded": True, "hosts": 3}
    assert calls == ["reload"]


def test_hosts_reload_route_contract_hides_reload_failure(client, monkeypatch):
    monkeypatch.setattr(
        worker,
        "reload_hosts",
        lambda: (3, "invalid hosts catalog"),
    )

    response = client.post("/api/hosts/reload")

    assert response.status_code == 500
    assert response.json == {"error": "Hosts configuration reload failed"}
