from concurrent.futures import Future
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from cancel_router import create_cancel_router


def _build_app(*, claims=None, entry=None):
    resolved_claims = claims or {
        "labId": "lab-1",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "resourceType": "fmu",
    }
    future = MagicMock(spec=Future)
    resolved_entry = entry or (future, "lab-1", "res-1", "puc-1", "executor")

    async def verify_jwt():
        return resolved_claims

    enforce_fmu_claim = MagicMock()
    ensure_local_execution_backend = MagicMock()
    get_running_entry = MagicMock(return_value=resolved_entry)
    get_claim_lab_id = MagicMock(side_effect=lambda current_claims: current_claims.get("labId"))
    normalize_lab_id = MagicMock(side_effect=lambda value: str(value).strip() if value else None)
    claim_reservation_key = MagicMock(
        side_effect=lambda current_claims: str(current_claims.get("reservationKey") or "").strip().lower()
    )
    shutdown_executor = MagicMock()
    finalize_tracking = MagicMock()

    app = FastAPI()
    app.include_router(create_cancel_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        ensure_local_execution_backend=ensure_local_execution_backend,
        get_running_entry=get_running_entry,
        get_claim_lab_id=get_claim_lab_id,
        normalize_lab_id=normalize_lab_id,
        claim_reservation_key=claim_reservation_key,
        shutdown_executor=shutdown_executor,
        finalize_tracking=finalize_tracking,
    ))
    return (
        app,
        future,
        enforce_fmu_claim,
        ensure_local_execution_backend,
        get_running_entry,
        get_claim_lab_id,
        normalize_lab_id,
        claim_reservation_key,
        shutdown_executor,
        finalize_tracking,
    )


def test_cancel_router_preserves_authorized_cancellation_and_cleanup():
    app, future, enforce_claim, ensure_backend, get_entry, get_lab_id, normalize_lab_id, claim_reservation_key, shutdown, finalize = _build_app(
        claims={
            "labId": "lab-1",
            "reservationKey": "RES-1",
            "pucHash": "PUC-1",
            "resourceType": "fmu",
        }
    )

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 200
    assert response.json() == {"status": "cancelled"}
    enforce_claim.assert_called_once()
    ensure_backend.assert_called_once_with("Simulation cancel endpoint")
    get_entry.assert_called_once_with("sim-1")
    get_lab_id.assert_called_once()
    normalize_lab_id.assert_called_once_with("lab-1")
    claim_reservation_key.assert_called_once()
    future.cancel.assert_called_once_with()
    shutdown.assert_called_once_with("executor", force=True)
    finalize.assert_called_once_with("sim-1")


def test_cancel_router_returns_not_found_without_side_effects():
    app, future, _enforce_claim, _ensure_backend, get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app(
        entry=None
    )
    get_entry.return_value = None

    response = TestClient(app).post("/api/v1/simulations/missing/cancel")

    assert response.status_code == 404
    assert response.json() == {"detail": "Simulation not found or already finished"}
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()


def test_cancel_router_propagates_claim_validation_errors():
    app, future, enforce_claim, ensure_backend, _get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app()
    enforce_claim.side_effect = HTTPException(status_code=403, detail="FMU access required")

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 403
    assert response.json() == {"detail": "FMU access required"}
    ensure_backend.assert_not_called()
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()


def test_cancel_router_propagates_backend_validation_errors():
    app, future, _enforce_claim, ensure_backend, _get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app()
    ensure_backend.side_effect = HTTPException(status_code=503, detail="local backend required")

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 503
    assert response.json() == {"detail": "local backend required"}
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()


def test_cancel_router_rejects_simulation_from_another_lab():
    app, future, _enforce_claim, _ensure_backend, _get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app(
        claims={"labId": "lab-2", "reservationKey": "res-1", "pucHash": "puc-1"}
    )

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 403
    assert response.json() == {"detail": "Token is not authorised for requested simulation"}
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()


def test_cancel_router_rejects_simulation_from_another_reservation():
    app, future, _enforce_claim, _ensure_backend, _get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app(
        claims={"labId": "lab-1", "reservationKey": "res-2", "pucHash": "puc-1"}
    )

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 403
    assert response.json() == {"detail": "Token is not authorised for requested simulation"}
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()


def test_cancel_router_rejects_simulation_from_another_puc():
    app, future, _enforce_claim, _ensure_backend, _get_entry, _get_lab_id, _normalize_lab_id, _claim_reservation_key, shutdown, finalize = _build_app(
        claims={"labId": "lab-1", "reservationKey": "res-1", "pucHash": "puc-2"}
    )

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 403
    assert response.json() == {"detail": "Token is not authorised for requested simulation"}
    future.cancel.assert_not_called()
    shutdown.assert_not_called()
    finalize.assert_not_called()
