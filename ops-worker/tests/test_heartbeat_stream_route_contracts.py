import worker


def test_heartbeat_stream_route_contract_requires_host(client):
    response = client.get("/api/heartbeat/stream")

    assert response.status_code == 400
    assert response.json == {"error": "host is required"}


def test_heartbeat_stream_route_contract_returns_not_found_for_unknown_host(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.get("/api/heartbeat/stream?host=missing")

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found"}


def test_heartbeat_stream_route_contract_preserves_sse_headers_and_query_flag(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))

    def fake_stream(host_arg, include_events):
        calls.append((host_arg, include_events))
        yield "event: heartbeat\ndata: {}\n\n"

    monkeypatch.setattr(worker, "generate_heartbeat_stream", fake_stream)

    response = client.get(
        "/api/heartbeat/stream?host=lab-ws-01&include_events=off"
    )

    assert response.status_code == 200
    assert response.content_type == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.get_data(as_text=True) == "event: heartbeat\ndata: {}\n\n"
    assert calls == [(host, False)]
