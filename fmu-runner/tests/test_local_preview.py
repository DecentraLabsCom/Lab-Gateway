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
    app = FastAPI()
    app.include_router(create_preview_router(PreviewTickets(), "private-development-credential"))
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
