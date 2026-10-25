from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from catalog_router import create_catalog_router


def _client(*, claims, policy=None, public_metadata_payload=None):
    async def verify():
        return claims

    enforce_claim = MagicMock()
    get_metadata = AsyncMock(return_value={"internal": "metadata"})
    public_metadata = MagicMock(return_value=public_metadata_payload or {"modelName": "Demo"})
    list_fmus = AsyncMock(return_value={"fmus": [{"filename": "demo.fmu"}]})
    async def get_policy(_claims):
        return policy

    app = FastAPI()
    app.include_router(create_catalog_router(
        verify_jwt=verify,
        enforce_fmu_claim=enforce_claim,
        get_authorized_model_metadata=get_metadata,
        public_model_metadata=public_metadata,
        list_authorized_fmu=list_fmus,
        get_effective_policy=get_policy if policy is not None else None,
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
        include_internal_variables=False,
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


def test_provider_describe_does_not_require_reservation_access_policy():
    async def verify():
        return {"accessKey": "demo.fmu", "scope": "fmu:describe", "purpose": "provider-describe"}

    get_policy = AsyncMock(side_effect=AssertionError("provider describe has no consumer policy context"))
    app = FastAPI()
    app.include_router(create_catalog_router(
        verify_jwt=verify,
        enforce_fmu_claim=MagicMock(),
        get_authorized_model_metadata=AsyncMock(return_value={"modelVariables": []}),
        public_model_metadata=lambda value: {"modelVariables": []},
        list_authorized_fmu=AsyncMock(),
        get_effective_policy=get_policy,
    ))

    response = TestClient(app).get("/api/v1/simulations/describe?fmuFileName=demo.fmu")

    assert response.status_code == 200
    assert response.json() == {"modelVariables": []}
    get_policy.assert_not_awaited()


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


def test_describe_and_effective_permissions_hide_denied_variables():
    policy = {
        "policySource": "fmi-default",
        "policyVersion": "opaque-digest",
        "variables": {
            "command": {"read": False, "writeAt": ["initialization"]},
            "speed": {"read": True, "writeAt": []},
            "secret": {"read": False, "writeAt": []},
        },
        "modelVariables": [
            {"name": "command", "causality": "input", "start": 0.0},
            {"name": "speed", "causality": "output", "start": 0.0},
        ],
    }
    public = {
        "modelName": "Demo",
        "modelVariables": [
            {"name": "command", "causality": "input"},
            {"name": "speed", "causality": "output"},
            {"name": "secret", "causality": "output"},
        ],
    }
    _, client, _, _, _, _ = _client(
        claims={
            "labId": "lab-1", "accessKey": "demo.fmu", "resourceType": "fmu",
            "reservationKey": "res-1", "pucHash": "puc-1",
        },
        policy=policy,
        public_metadata_payload=public,
    )

    describe = client.get("/api/v1/simulations/describe?fmuFileName=demo.fmu")
    access = client.get("/api/v1/simulations/access")

    assert describe.status_code == 200
    assert [item["name"] for item in describe.json()["modelVariables"]] == ["command", "speed"]
    assert access.status_code == 200
    assert access.json() == {
        "policySource": "fmi-default",
        "policyVersion": "opaque-digest",
        "variables": {
            "command": {"read": False, "writeAt": ["initialization"]},
            "speed": {"read": True, "writeAt": []},
        },
        "modelVariables": [
            {"name": "command", "causality": "input"},
            {"name": "speed", "causality": "output", "start": 0},
        ],
    }
