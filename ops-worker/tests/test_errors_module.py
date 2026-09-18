import requests
from winrm.exceptions import InvalidCredentialsError

import errors


def test_winrm_trust_error_payload_contract_normalizes_codes_and_adds_correlation():
    assert errors.build_winrm_trust_error_payload(
        "lab-ws-01",
        "WINRM_TLS_FAILED",
        request_id=lambda: "request-1",
    ) == {
        "error": errors.WINRM_TLS_FAILED_MESSAGE,
        "code": "WINRM_TLS_FAILED",
        "host": "lab-ws-01",
        "requestId": "request-1",
    }
    assert errors.build_winrm_trust_error_payload(
        "lab-ws-01",
        "not-a-public-code",
        request_id=lambda: "request-2",
    )["code"] == "WINRM_TRUST_INVALID"


def test_winrm_error_contract_is_exposed_from_the_dedicated_module():
    error = errors.WinRMTrustError(
        errors.WINRM_TRUST_REQUIRED_CODE,
        errors.WINRM_TRUST_REQUIRED_MESSAGE,
    )

    assert isinstance(error, ValueError)
    assert error.code == "WINRM_TRUST_REQUIRED"
    assert str(error) == "WinRM certificate trust is required"
    assert errors.WINRM_TRUST_ERROR_MESSAGES[error.code] == str(error)


def test_missing_credentials_predicate_preserves_the_existing_error_message():
    missing = ValueError(errors.WINRM_CREDENTIALS_REQUIRED_MESSAGE)

    assert errors.is_missing_winrm_credentials_error(missing) is True
    assert errors.is_missing_winrm_credentials_error(ValueError("other")) is False
    assert errors.is_missing_winrm_credentials_error(RuntimeError(str(missing))) is False


def test_winrm_unreachable_error_contract_classifies_network_failures_only():
    assert errors.is_winrm_unreachable_error(
        requests.exceptions.ConnectTimeout("station is off")
    ) is True
    assert errors.is_winrm_unreachable_error(
        requests.exceptions.ConnectionError("connection refused")
    ) is True
    assert errors.is_winrm_unreachable_error(
        requests.exceptions.SSLError("certificate verify failed")
    ) is False
    assert errors.is_winrm_unreachable_error(ValueError("invalid heartbeat JSON")) is False


def test_winrm_unreachable_payload_contains_safe_station_endpoint_details():
    assert errors.build_winrm_unreachable_payload(
        "lab-ws-01",
        {"address": "192.168.1.50", "winrm_port": 5986},
    ) == {
        "error": errors.WINRM_UNREACHABLE_MESSAGE,
        "code": errors.WINRM_UNREACHABLE_CODE,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "port": 5986,
    }

def test_winrm_authentication_error_classifier_handles_pywinrm_and_http_401():
    class AuthenticationError(Exception):
        code = 401

    response = requests.Response()
    response.status_code = 401
    http_error = requests.exceptions.HTTPError(response=response)

    assert errors.is_winrm_authentication_error(AuthenticationError()) is True
    assert errors.is_winrm_authentication_error(InvalidCredentialsError("rejected")) is True
    assert errors.is_winrm_authentication_error(http_error) is True
    assert errors.is_winrm_authentication_error(requests.exceptions.Timeout()) is False
    assert errors.is_winrm_authentication_error(requests.exceptions.SSLError()) is False


def test_winrm_heartbeat_error_payload_is_safe_and_correlated():
    assert errors.build_winrm_heartbeat_error_payload(
        "lab-ws-01",
        "WINRM_HEARTBEAT_NOT_FOUND",
        request_id=lambda: "heartbeat-1",
    ) == {
        "error": errors.WINRM_HEARTBEAT_NOT_FOUND_MESSAGE,
        "code": "WINRM_HEARTBEAT_NOT_FOUND",
        "host": "lab-ws-01",
        "requestId": "heartbeat-1",
    }
    assert errors.winrm_heartbeat_error_status("WINRM_AUTH_FAILED") == 409
    assert errors.winrm_heartbeat_error_status("WINRM_HEARTBEAT_INVALID") == 502
