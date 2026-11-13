from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from proxy_router import create_proxy_router


def _build_test_app(
    *, claims: dict, issue_ticket: AsyncMock | None = None, access_policy=None, model_metadata=None,
):
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
        return model_metadata or {"fmiVersion": "2.0"}

    async def get_effective_policy(_claims):
        return access_policy

    model_description_builder = MagicMock(return_value=b"<xml />")
    app.state.model_description_builder = model_description_builder

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
        get_effective_policy=get_effective_policy if access_policy is not None else None,
        build_proxy_model_description_xml=model_description_builder,
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


def test_browser_connection_uses_the_same_reservation_ticket_without_building_an_fmu():
    app, issue_ticket, _, enforce_reservation, rate_limit = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"}
    )
    response = TestClient(app).post(
        "/api/v1/fmu/connection/42?reservationKey=0xabc", headers={"Authorization": "Bearer booking-token"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "protocolVersion": "1.0", "gatewayWsUrl": "wss://gateway.example/fmu/api/v1/fmu/sessions",
        "labId": "42", "reservationKey": "0xabc", "sessionTicket": "st_ticket_1", "ticketExpiresAt": 4102444800,
    }
    assert response.headers["cache-control"] == "no-store"
    issue_ticket.assert_awaited_once()
    enforce_reservation.assert_called_once()
    rate_limit.assert_called_once_with("user-1:42")


def test_proxy_model_description_exposes_only_effectively_readable_or_writable_variables():
    from simulation_access_policy import build_effective_policy

    metadata = {
        "fmiVersion": "2.0",
        "simulationKind": "coSimulation",
        "supportsCoSimulation": True,
        "modelVariables": [
            {"name": "command", "causality": "input", "variability": "continuous", "start": 2},
            {"name": "speed", "causality": "output", "variability": "continuous", "start": 0},
            {"name": "secret", "causality": "output", "variability": "continuous", "start": 0},
        ],
    }
    policy = build_effective_policy(
        metadata,
        overrides={"command": {"read": False}, "secret": {"read": False}},
    )
    policy["authorizedExecutionInterfaces"] = ["CoSimulation"]
    app, *_ = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"},
        access_policy=policy,
        model_metadata=metadata,
    )

    response = TestClient(app).get(
        "/api/v1/fmu/proxy/42?reservationKey=0xabc",
        headers={"Authorization": "Bearer booking-token"},
    )

    assert response.status_code == 200
    model_description = app.state.model_description_builder.call_args.args[0]
    assert [variable["name"] for variable in model_description["modelVariables"]] == ["command", "speed"]
    assert "start" not in model_description["modelVariables"][0]


def test_proxy_router_preserves_local_model_exchange_state_variables():
    metadata = {
        "fmiVersion": "3.0",
        "simulationKind": "modelExchange",
        "supportsModelExchange": True,
        "availableExecutionInterfaces": ["ModelExchange"],
        "modelVariables": [
            {"name": "height", "causality": "local", "type": "Float64", "valueReference": 10},
            {"name": "der_height", "causality": "local", "type": "Float64", "valueReference": 20},
            {"name": "impact", "causality": "local", "type": "Float64", "valueReference": 30},
            {"name": "internal_factor", "causality": "local", "type": "Float64", "valueReference": 50},
            {"name": "algebraic_state", "causality": "local", "type": "Float64", "valueReference": 60},
            {"name": "residual_value", "causality": "local", "type": "Float64", "valueReference": 70},
            {"name": "unused_internal", "causality": "local", "type": "Float64", "valueReference": 80},
            {"name": "m", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 90, "start": 2},
            {"name": "n", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 91, "start": 2},
            {"name": "r", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 92, "start": 1},
            {
                "name": "state_matrix", "causality": "parameter", "type": "Float64",
                "valueReference": 41, "dimensions": [{"valueReference": 90}, {"valueReference": 91}],
            },
            {
                "name": "input_vector", "causality": "input", "type": "Float64",
                "valueReference": 42, "dimensions": [{"valueReference": 92}],
            },
            {"name": "ground", "causality": "parameter", "type": "Float64", "valueReference": 40},
        ],
        "modelStructure": {
            "derivatives": [{
                "name": "der_height", "valueReference": 20, "stateValueReference": 10,
                "dependencies": [50], "dependencyNames": ["internal_factor"],
            }],
            "eventIndicators": [{"name": "impact", "valueReference": 30}],
        },
        "fmiLsDae": {
            "algebraicVariables": ["algebraic_state"],
            "algebraicValueReferences": [60],
            "residualVariables": [{"name": "residual_value", "valueReference": 70}],
            "modelStructure": {"residuals": [{"valueReference": 70, "dependencies": [60]}]},
        },
    }
    app, *_ = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"},
        access_policy={"variables": {}, "authorizedExecutionInterfaces": ["ModelExchange"]},
        model_metadata=metadata,
    )

    response = TestClient(app).get(
        "/api/v1/fmu/proxy/42?reservationKey=0xabc",
        headers={"Authorization": "Bearer booking-token"},
    )

    assert response.status_code == 200
    proxy_metadata = app.state.model_description_builder.call_args.args[0]
    assert [variable["name"] for variable in proxy_metadata["modelVariables"]] == [
        "height", "der_height", "impact", "internal_factor", "algebraic_state", "residual_value",
        "m", "n", "r", "state_matrix", "input_vector", "ground",
    ]
    assert proxy_metadata["modelStructure"] == metadata["modelStructure"]
    assert proxy_metadata["authorizedExecutionInterfaces"] == ["ModelExchange"]


def test_proxy_router_omits_local_variables_for_cosimulation_only_proxy():
    metadata = {
        "fmiVersion": "2.0",
        "simulationKind": "coSimulation",
        "supportsCoSimulation": True,
        "availableExecutionInterfaces": ["CoSimulation"],
        "modelVariables": [
            {"name": "command", "causality": "input", "type": "Real", "valueReference": 1},
            {"name": "speed", "causality": "output", "type": "Real", "valueReference": 2},
            {"name": "internal_state", "causality": "local", "type": "Real", "valueReference": 3},
        ],
    }
    app, *_ = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"},
        model_metadata=metadata,
    )

    response = TestClient(app).get(
        "/api/v1/fmu/proxy/42?reservationKey=0xabc",
        headers={"Authorization": "Bearer booking-token"},
    )

    assert response.status_code == 200
    proxy_metadata = app.state.model_description_builder.call_args.args[0]
    assert [variable["name"] for variable in proxy_metadata["modelVariables"]] == ["command", "speed"]


def test_proxy_router_preserves_local_dimension_constants_for_cosimulation_without_permissions():
    metadata = {
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "supportsCoSimulation": True,
        "availableExecutionInterfaces": ["CoSimulation"],
        "modelVariables": [
            {"name": "command", "causality": "input", "type": "Float64", "valueReference": 1},
            {"name": "speed", "causality": "output", "type": "Float64", "valueReference": 2},
            {"name": "unused_internal", "causality": "local", "type": "Float64", "valueReference": 3},
            {"name": "m", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 90, "start": 2},
            {"name": "n", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 91, "start": 2},
            {"name": "r", "causality": "local", "type": "UInt64", "variability": "constant", "valueReference": 92, "start": 1},
            {
                "name": "state_matrix", "causality": "parameter", "type": "Float64",
                "valueReference": 41, "dimensions": [{"valueReference": 90}, {"valueReference": 91}],
            },
            {
                "name": "input_vector", "causality": "input", "type": "Float64",
                "valueReference": 42, "dimensions": [{"valueReference": 92}],
            },
        ],
        "modelStructure": {"outputs": [{"name": "speed", "valueReference": 2, "dependencies": [3]}]},
    }
    access_policy = {
        "variables": {
            "command": {"read": False, "writeAt": ["initialization"]},
            "speed": {"read": True, "writeAt": []},
            "state_matrix": {"read": False, "writeAt": ["initialization"]},
            "input_vector": {"read": False, "writeAt": ["initialization"]},
        },
        "authorizedExecutionInterfaces": ["CoSimulation"],
    }
    app, *_ = _build_test_app(
        claims={"sub": "user-1", "labId": "42", "accessKey": "model.fmu", "reservationKey": "0xabc"},
        access_policy=access_policy,
        model_metadata=metadata,
    )

    response = TestClient(app).get(
        "/api/v1/fmu/proxy/42?reservationKey=0xabc",
        headers={"Authorization": "Bearer booking-token"},
    )

    assert response.status_code == 200
    proxy_metadata = app.state.model_description_builder.call_args.args[0]
    variables = proxy_metadata["modelVariables"]
    assert [variable["name"] for variable in variables] == [
        "command", "speed", "m", "n", "r", "state_matrix", "input_vector",
    ]
    assert {variable["name"]: variable["start"] for variable in variables if variable["name"] in {"m", "n", "r"}} == {
        "m": 2, "n": 2, "r": 1,
    }
    assert not {"m", "n", "r"} & access_policy["variables"].keys()
