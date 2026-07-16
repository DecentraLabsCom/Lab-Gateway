import worker


def test_api_rejects_missing_internal_token(client):
    response = client.get(
        "/api/hosts",
        headers={worker.OPS_INTERNAL_AUTH_HEADER: ""},
    )

    assert response.status_code == 401


def test_api_rejects_wrong_internal_token(client):
    response = client.get(
        "/api/hosts",
        headers={worker.OPS_INTERNAL_AUTH_HEADER: "wrong-token"},
    )

    assert response.status_code == 401


def test_api_accepts_gateway_internal_token(client):
    response = client.get(
        "/api/hosts",
        headers={worker.OPS_INTERNAL_AUTH_HEADER: worker.OPS_INTERNAL_AUTH_TOKEN},
    )

    assert response.status_code == 200


def test_health_remains_public(client):
    response = client.get("/health")

    # Health may report dependency failure in a unit-test environment, but it
    # must not be rejected by the Ops internal-auth gate.
    assert response.status_code != 401
    assert response.status_code != 403


def test_api_fails_closed_when_internal_token_is_unconfigured(client, monkeypatch):
    monkeypatch.setattr(worker, "OPS_INTERNAL_AUTH_TOKEN", "")

    response = client.get(
        "/api/hosts",
        headers={worker.OPS_INTERNAL_AUTH_HEADER: "anything"},
    )

    assert response.status_code == 503
