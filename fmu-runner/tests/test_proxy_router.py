from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from proxy_router import create_proxy_router


def _build_test_app(*, claims: dict, issue_ticket: AsyncMock | None = None):
    app = FastAPI()
    issue_ticket = issue_ticket or AsyncMock(return_value=("st_ticket_1", 4102444800))
    enforce_fmu_claim = MagicMock()
    enforce_requested_reservation = MagicMock()
    allow_proxy_download = MagicMock(return_value=True)

    async def verify_jwt():
        return claims

    def extract_authorization_header(request):
        return request.headers.get("authorization")

    async def get_authorized_model_metadata(**_kwargs):
        return {"fmiVersion": "2.0"}

    router = create_proxy_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        get_claim_lab_id=lambda _claims: "42",
        enforce_requested_reservation=enforce_requested_reservation,
        allow_proxy_download=allow_proxy_download,
        extract_authorization_header=extract_authorization_header,
        new_request_id=lambda: "proxy_test",
        issue_session_ticket=issue_ticket,
        derive_gateway_ws_url=MagicMock(return_value="wss://gateway.example/fmu/api/v1/fmu/sessions"),
        get_authorized_model_metadata=get_authorized_model_metadata,
        build_proxy_model_description_xml=MagicMock(return_value=b"<xml />"),
        parse_fmi_major_version=MagicMock(return_value=2),
        proxy_model_identifier=MagicMock(return_value="decentralabs_proxy"),
        collect_runtime_files=MagicMock(return_value=[]),
        build_proxy_session_config=MagicMock(return_value={"sessionTicket": "st_ticket_1"}),
        build_proxy_artifact=MagicMock(return_value=b"proxy-artifact"),
        build_proxy_artifact_headers=MagicMock(return_value={
            "Content-Disposition": 'attachment; filename="fmu-proxy-lab-42.fmu"',
            "X-Proxy-Artifact-Sha256": "sha256",
        }),
        normalize_ticket_id=MagicMock(return_value="st_ticket_1"),
        get_signing_key=lambda: "",
        logger=MagicMock(),
    )
    app.include_router(router)
    return app, issue_ticket, enforce_fmu_claim, enforce_requested_reservation, allow_proxy_download


def test_proxy_router_preserves_successful_download_composition():
    app, issue_ticket, enforce_fmu_claim, enforce_requested_reservation, allow_proxy_download = _build_test_app(
        claims={
            "sub": "user-1",
            "labId": "42",
            "accessKey": "model.fmu",
            "reservationKey": "0xabc",
        }
    )

    response = TestClient(app).get(
        "/api/v1/fmu/proxy/42?reservationKey=0xabc",
        headers={"Authorization": "Bearer booking-token"},
    )

    assert response.status_code == 200
    assert response.content == b"proxy-artifact"
    enforce_fmu_claim.assert_called_once()
    enforce_requested_reservation.assert_called_once_with(
        {"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"},
        "0xabc",
    )
    allow_proxy_download.assert_called_once_with("user-1:42")
    issue_ticket.assert_awaited_once()


def test_proxy_router_requires_authorization_before_issuing_ticket():
    app, issue_ticket, _enforce_fmu_claim, _enforce_requested_reservation, _allow_proxy_download = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"}
    )

    response = TestClient(app).get("/api/v1/fmu/proxy/42?reservationKey=0xabc")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token required to issue session ticket"
    issue_ticket.assert_not_awaited()
