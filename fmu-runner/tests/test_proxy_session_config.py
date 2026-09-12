import pytest

from proxy_session_config import (
    build_proxy_session_config,
    derive_gateway_ws_url,
)


def test_derive_gateway_ws_url_prefers_explicit_configuration():
    assert derive_gateway_ws_url(
        {"aud": "https://claims.example/auth"},
        configured_url="wss://configured.example/fmu/api/v1/fmu/sessions",
    ) == "wss://configured.example/fmu/api/v1/fmu/sessions"


def test_derive_gateway_ws_url_maps_https_audience_to_wss():
    assert derive_gateway_ws_url(
        {"aud": "https://gateway.example/auth"},
        configured_url="",
    ) == "wss://gateway.example/fmu/api/v1/fmu/sessions"


def test_derive_gateway_ws_url_maps_http_audience_to_ws():
    assert derive_gateway_ws_url(
        {"aud": "http://gateway.example/auth"},
        configured_url="",
    ) == "ws://gateway.example/fmu/api/v1/fmu/sessions"


@pytest.mark.parametrize(
    "claims, message",
    [
        ({}, "Missing aud claim required to derive gateway WS URL"),
        ({"aud": "not-a-url"}, "Invalid aud claim required to derive gateway WS URL"),
    ],
)
def test_derive_gateway_ws_url_rejects_missing_or_invalid_audience(claims, message):
    with pytest.raises(ValueError, match=message):
        derive_gateway_ws_url(claims, configured_url="")


def test_build_proxy_session_config_preserves_runtime_contract():
    assert build_proxy_session_config(
        fmi_version="3.0",
        gateway_ws_url="wss://gateway.example/fmu/api/v1/fmu/sessions",
        lab_id="42",
        reservation_key="0xabc",
        session_ticket="st_ticket_1",
        ticket_expires_at=4102444800,
    ) == {
        "protocolVersion": "1.0",
        "fmiVersion": "3.0",
        "gatewayWsUrl": "wss://gateway.example/fmu/api/v1/fmu/sessions",
        "labId": "42",
        "reservationKey": "0xabc",
        "sessionTicket": "st_ticket_1",
        "ticketExpiresAt": 4102444800,
        "timeMode": "simtime",
    }
