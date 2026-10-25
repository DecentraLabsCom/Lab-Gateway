import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_preview import PreviewTickets, create_preview_router


def test_preview_ticket_is_one_use_and_bound_before_consumption():
    store = PreviewTickets()
    grant = store.issue("example.fmu")
    with pytest.raises(HTTPException) as error:
        store.redeem(grant["sessionTicket"], "other", grant["reservationKey"])
    assert error.value.status_code == 403
    assert store.redeem(grant["sessionTicket"], grant["labId"], grant["reservationKey"])["accessKey"] == "example.fmu"
    with pytest.raises(HTTPException):
        store.redeem(grant["sessionTicket"], grant["labId"], grant["reservationKey"])


def test_preview_issuance_requires_the_private_bridge_credential():
    async def provision(_claims):
        return {"policySource": "aas-generated"}

    app = FastAPI()
    app.include_router(create_preview_router(
        PreviewTickets(),
        "private-development-credential",
        ensure_aas_policy=provision,
    ))
    client = TestClient(app)
    assert client.post("/internal/dev/fmu/connection", json={"accessKey": "example.fmu"}).status_code == 403
    assert client.post("/internal/dev/fmu/connection", json={"accessKey": "example.fmu"}, headers={"X-Local-Preview-Token": "private-development-credential"}).status_code == 200


def test_preview_ticket_expires(monkeypatch):
    store = PreviewTickets()
    monkeypatch.setattr("local_preview.time.time", lambda: 100)
    grant = store.issue("example.fmu")
    monkeypatch.setattr("local_preview.time.time", lambda: 161)
    with pytest.raises(HTTPException):
        store.redeem(grant["sessionTicket"], grant["labId"], grant["reservationKey"])


def test_preview_claims_have_a_stable_aas_lab_identity_per_fmu():
    store = PreviewTickets()
    first = store.claims_for_access_key("demo/model.fmu")
    second = store.claims_for_access_key("demo/model.fmu")
    other = store.claims_for_access_key("demo/other.fmu")

    assert first["labId"] == second["labId"]
    assert first["labId"].startswith("local_demo_")
    assert ":" not in first["labId"]
    assert first["reservationKey"] == second["reservationKey"]
    assert first["labId"] != other["labId"]


def test_preview_connection_provisions_and_requires_an_aas_policy():
    async def provision(claims):
        assert claims["labId"].startswith("local_demo_")
        assert claims["exp"] == claims["reservationEndsAt"]
        return {"policySource": "aas-generated"}

    app = FastAPI()
    app.include_router(create_preview_router(
        PreviewTickets(),
        "private-development-credential",
        ensure_aas_policy=provision,
    ))
    client = TestClient(app)
    response = client.post(
        "/internal/dev/fmu/connection",
        json={"accessKey": "example.fmu"},
        headers={"X-Local-Preview-Token": "private-development-credential"},
    )

    assert response.status_code == 200
    assert response.json()["labId"].startswith("local_demo_")


def test_preview_connection_fails_closed_when_aas_policy_is_unavailable():
    async def provision(_claims):
        raise HTTPException(status_code=503, detail="AAS is unavailable")

    app = FastAPI()
    app.include_router(create_preview_router(
        PreviewTickets(),
        "private-development-credential",
        ensure_aas_policy=provision,
    ))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/internal/dev/fmu/connection",
        json={"accessKey": "example.fmu"},
        headers={"X-Local-Preview-Token": "private-development-credential"},
    )

    assert response.status_code == 503
