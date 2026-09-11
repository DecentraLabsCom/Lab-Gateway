import json
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from history_router import create_history_router


def _client(*, claims=None):
    resolved_claims = claims or {
        "labId": "lab-1",
        "reservationKey": "0xABC",
        "pucHash": "PUC-HASH",
    }

    async def verify():
        return resolved_claims

    enforce_claim = MagicMock()
    ensure_local_backend = MagicMock()
    get_claim_lab_id = MagicMock(return_value="lab-1")
    normalize_lab_id = MagicMock(side_effect=lambda value: str(value).strip() if value else None)
    claim_reservation_key = MagicMock(return_value="0xabc")
    list_history = AsyncMock(return_value=[{"id": "sim-1"}])
    get_history_result = AsyncMock(return_value={
        "id": "sim-1",
        "parameters": json.dumps({"mass": 1.5}),
        "options": json.dumps({"stopTime": 1}),
        "result": json.dumps({"time": [0, 1]}),
    })
    app = FastAPI()
    app.include_router(create_history_router(
        verify_jwt=verify,
        enforce_fmu_claim=enforce_claim,
        ensure_local_execution_backend=ensure_local_backend,
        get_claim_lab_id=get_claim_lab_id,
        normalize_lab_id=normalize_lab_id,
        claim_reservation_key=claim_reservation_key,
        get_history_db_path=lambda: "history.db",
        list_history=list_history,
        get_history_result=get_history_result,
    ))
    return (
        TestClient(app),
        enforce_claim,
        ensure_local_backend,
        get_claim_lab_id,
        normalize_lab_id,
        claim_reservation_key,
        list_history,
        get_history_result,
    )


def test_history_route_scopes_and_paginates_authorized_rows():
    client, enforce_claim, ensure_local_backend, get_claim_lab_id, normalize_lab_id, claim_reservation_key, list_history, _ = _client()

    response = client.get("/api/v1/simulations/history?labId=lab-1&limit=5&offset=10")

    assert response.status_code == 200
    assert response.json() == {"simulations": [{"id": "sim-1"}]}
    enforce_claim.assert_called_once_with({
        "labId": "lab-1",
        "reservationKey": "0xABC",
        "pucHash": "PUC-HASH",
    })
    ensure_local_backend.assert_called_once_with("Simulation history endpoint")
    get_claim_lab_id.assert_called_once()
    normalize_lab_id.assert_called_once_with("lab-1")
    claim_reservation_key.assert_called_once()
    list_history.assert_awaited_once_with(
        "history.db",
        lab_id="lab-1",
        reservation_key="0xabc",
        puc_hash="puc-hash",
        limit=5,
        offset=10,
    )


def test_result_route_decodes_json_columns():
    client, enforce_claim, ensure_local_backend, get_claim_lab_id, _, claim_reservation_key, _, get_history_result = _client()

    response = client.get("/api/v1/simulations/sim-1/result")

    assert response.status_code == 200
    assert response.json() == {
        "id": "sim-1",
        "parameters": {"mass": 1.5},
        "options": {"stopTime": 1},
        "result": {"time": [0, 1]},
    }
    enforce_claim.assert_called_once()
    ensure_local_backend.assert_called_once_with("Simulation result endpoint")
    get_claim_lab_id.assert_called_once()
    claim_reservation_key.assert_called_once()
    get_history_result.assert_awaited_once_with(
        "history.db",
        sim_id="sim-1",
        lab_id="lab-1",
        reservation_key="0xabc",
        puc_hash="puc-hash",
    )


def test_history_route_rejects_a_different_requested_lab():
    client, _, _, _, _, _, list_history, _ = _client()

    response = client.get("/api/v1/simulations/history?labId=other-lab")

    assert response.status_code == 403
    assert response.json() == {"detail": "Token is not authorised for requested labId"}
    list_history.assert_not_awaited()


def test_result_route_returns_not_found_for_an_out_of_scope_simulation():
    client, _, _, _, _, _, _, get_history_result = _client()
    get_history_result.return_value = None

    response = client.get("/api/v1/simulations/missing/result")

    assert response.status_code == 404
    assert response.json() == {"detail": "Simulation not found"}


def test_history_route_preserves_local_backend_errors():
    client, _, ensure_local_backend, _, _, _, _, _ = _client()
    ensure_local_backend.side_effect = HTTPException(status_code=503, detail="local backend required")

    response = client.get("/api/v1/simulations/history")

    assert response.status_code == 503
    assert response.json() == {"detail": "local backend required"}