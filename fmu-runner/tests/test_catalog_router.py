from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from catalog_router import create_catalog_router


def _client(*, claims):
    async def verify():
        return claims

    enforce_claim = MagicMock()
    get_metadata = AsyncMock(return_value={"internal": "metadata"})
    public_metadata = MagicMock(return_value={"modelName": "Demo"})
    list_fmus = AsyncMock(return_value={"fmus": [{"filename": "demo.fmu"}]})
    app = FastAPI()
    app.include_router(create_catalog_router(
        verify_jwt=verify,
        enforce_fmu_claim=enforce_claim,
        get_authorized_model_metadata=get_metadata,
        public_model_metadata=public_metadata,
        list_authorized_fmu=list_fmus,
    ))
    return app, TestClient(app), enforce_claim, get_metadata, public_metadata, list_fmus


def test_describe_route_enforces_provider_describe_and_returns_public_metadata():
    _, client, enforce_claim, get_metadata, public_metadata, _ = _client(
        claims={"accessKey": "demo.fmu"},
    )

    response = client.get("/api/v1/simulations/describe?fmuFileName=demo.fmu")

    assert response.status_code == 200
    assert response.json() == {"modelName": "Demo"}
    enforce_claim.assert_called_once_with({"accessKey": "demo.fmu"}, allow_provider_describe=True)
    get_metadata.assert_awaited_once_with(
        claims={"accessKey": "demo.fmu"},
        requested_fmu_filename="demo.fmu",
    )
    public_metadata.assert_called_once_with({"internal": "metadata"})


def test_list_route_enforces_regular_claims_and_returns_backend_payload():
    _, client, enforce_claim, _, _, list_fmus = _client(
        claims={"accessKey": "demo.fmu"},
    )

    response = client.get("/api/v1/fmu/list")

    assert response.status_code == 200
    assert response.json() == {"fmus": [{"filename": "demo.fmu"}]}
    enforce_claim.assert_called_once_with({"accessKey": "demo.fmu"})
    list_fmus.assert_awaited_once_with(claims={"accessKey": "demo.fmu"})


def test_describe_route_keeps_required_query_validation():
    _, client, _, _, _, _ = _client(claims={"accessKey": "demo.fmu"})

    response = client.get("/api/v1/simulations/describe")

    assert response.status_code == 422


def test_list_route_preserves_claim_guard_errors():
    async def verify():
        return {"accessKey": "demo.fmu"}

    def reject(_claims):
        raise HTTPException(status_code=403, detail="forbidden")

    app = FastAPI()
    app.include_router(create_catalog_router(
        verify_jwt=verify,
        enforce_fmu_claim=reject,
        get_authorized_model_metadata=AsyncMock(),
        public_model_metadata=lambda value: value,
        list_authorized_fmu=AsyncMock(),
    ))

    response = TestClient(app).get("/api/v1/fmu/list")

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}