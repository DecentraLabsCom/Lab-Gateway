import pytest

import winrm_credentials_resolution


def test_credentials_resolution_uses_the_host_reference_and_store_callback():
    calls = []
    host = {"name": "lab-ws-01"}

    def credential_ref_for_host(received_host):
        calls.append(("ref", received_host))
        return "lab-ws-01"

    def load_credentials(ref):
        calls.append(("load", ref))
        return {"user": "station-user", "password": "secret"}

    assert winrm_credentials_resolution.resolve_winrm_credentials(
        host,
        None,
        None,
        credential_ref_for_host=credential_ref_for_host,
        load_credentials=load_credentials,
        required_message="WinRM credentials are required",
    ) == ("station-user", "secret")
    assert calls == [("ref", host), ("load", "lab-ws-01")]


def test_credentials_resolution_rejects_request_credentials_and_missing_store_entry():
    host = {"name": "lab-ws-01"}
    dependencies = {
        "credential_ref_for_host": lambda _host: "lab-ws-01",
        "load_credentials": lambda _ref: None,
        "required_message": "WinRM credentials are required",
    }

    with pytest.raises(ValueError, match="stored through the credentials endpoint"):
        winrm_credentials_resolution.resolve_winrm_credentials(
            host,
            "user",
            None,
            **dependencies,
        )
    with pytest.raises(ValueError, match="WinRM credentials are required"):
        winrm_credentials_resolution.resolve_winrm_credentials(
            host,
            None,
            None,
            **dependencies,
        )
