from unittest.mock import Mock

import worker


def test_revocation_ingest_contract_is_disabled_without_gateway_token(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "")
    enqueue = Mock()
    monkeypatch.setattr(worker, "enqueue_guacamole_token_revocation", enqueue)

    response = client.post(
        "/internal/guacamole-token-revocations",
        json={"authToken": "secret-token"},
    )

    assert response.status_code == 503
    assert response.json == {
        "accepted": False,
        "error": "Guacamole revocation ingestion is disabled",
    }
    enqueue.assert_not_called()


def test_observation_ingest_contract_is_disabled_without_gateway_token(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "")
    enqueue = Mock()
    monkeypatch.setattr(worker, "enqueue_session_observation", enqueue)

    response = client.post(
        "/internal/session-observations",
        json={"dedupKey": "a" * 64},
    )

    assert response.status_code == 503
    assert response.json == {
        "accepted": False,
        "error": "session observation ingestion is disabled",
    }
    enqueue.assert_not_called()


def test_ingest_contract_rejects_wrong_gateway_token_for_both_routes(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    enqueue_revocation = Mock()
    enqueue_observation = Mock()
    monkeypatch.setattr(worker, "enqueue_guacamole_token_revocation", enqueue_revocation)
    monkeypatch.setattr(worker, "enqueue_session_observation", enqueue_observation)

    revocation = client.post(
        "/internal/guacamole-token-revocations",
        json={"authToken": "secret-token"},
        headers={"X-Gateway-Observation-Token": "wrong-token"},
    )
    observation = client.post(
        "/internal/session-observations",
        json={"dedupKey": "a" * 64},
        headers={"X-Gateway-Observation-Token": "wrong-token"},
    )

    assert revocation.status_code == 401
    assert revocation.json == {"accepted": False, "error": "unauthorized"}
    assert observation.status_code == 401
    assert observation.json == {"accepted": False, "error": "unauthorized"}
    enqueue_revocation.assert_not_called()
    enqueue_observation.assert_not_called()


def test_revocation_ingest_contract_forwards_json_and_returns_202(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    payload = {"authToken": "secret-token", "expiresAt": 1893456000}
    enqueue = Mock(return_value=True)
    monkeypatch.setattr(worker, "enqueue_guacamole_token_revocation", enqueue)

    response = client.post(
        "/internal/guacamole-token-revocations",
        json=payload,
        headers={"X-Gateway-Observation-Token": "gateway-token"},
    )

    assert response.status_code == 202
    assert response.json == {"accepted": True}
    enqueue.assert_called_once_with(payload)
    assert "secret-token" not in response.get_data(as_text=True)


def test_observation_ingest_contract_forwards_json_and_returns_202(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    payload = {"dedupKey": "a" * 64, "observedAt": 1893456000}
    enqueue = Mock(return_value=True)
    monkeypatch.setattr(worker, "enqueue_session_observation", enqueue)

    response = client.post(
        "/internal/session-observations",
        json=payload,
        headers={"X-Gateway-Observation-Token": "gateway-token"},
    )

    assert response.status_code == 202
    assert response.json == {"accepted": True}
    enqueue.assert_called_once_with(payload)


def test_ingest_contract_rejects_non_object_json_for_both_routes(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    enqueue_revocation = Mock()
    enqueue_observation = Mock()
    monkeypatch.setattr(worker, "enqueue_guacamole_token_revocation", enqueue_revocation)
    monkeypatch.setattr(worker, "enqueue_session_observation", enqueue_observation)
    headers = {"X-Gateway-Observation-Token": "gateway-token"}

    revocation = client.post("/internal/guacamole-token-revocations", json=["invalid"], headers=headers)
    observation = client.post("/internal/session-observations", json=["invalid"], headers=headers)

    assert revocation.status_code == 400
    assert revocation.json == {"accepted": False, "error": "invalid or unavailable revocation"}
    assert observation.status_code == 400
    assert observation.json == {"accepted": False, "error": "invalid or unavailable observation"}
    enqueue_revocation.assert_not_called()
    enqueue_observation.assert_not_called()


def test_ingest_contract_maps_unavailable_queue_to_400_for_both_routes(client, monkeypatch):
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "gateway-token")
    monkeypatch.setattr(worker, "enqueue_guacamole_token_revocation", Mock(return_value=False))
    monkeypatch.setattr(worker, "enqueue_session_observation", Mock(return_value=False))
    headers = {"X-Gateway-Observation-Token": "gateway-token"}

    revocation = client.post(
        "/internal/guacamole-token-revocations",
        json={"authToken": "secret-token"},
        headers=headers,
    )
    observation = client.post(
        "/internal/session-observations",
        json={"dedupKey": "a" * 64},
        headers=headers,
    )

    assert revocation.status_code == 400
    assert revocation.json == {"accepted": False, "error": "invalid or unavailable revocation"}
    assert observation.status_code == 400
    assert observation.json == {"accepted": False, "error": "invalid or unavailable observation"}
    assert "secret-token" not in revocation.get_data(as_text=True)
