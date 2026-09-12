from datetime import datetime, timezone

import pytest

import errors
import winrm_trust_service


def _dependencies(*, exists=True, persisted=None, validation_error=None):
    certificate = object()
    calls = []

    def validate(received_certificate, host):
        calls.append(("validate", received_certificate, host))
        if validation_error is not None:
            raise validation_error
        return {"status": "ready"}

    return {
        "trust_ref_for_host": lambda host: "pc-siemens",
        "certificate_path_for_host": lambda host: "/trust/pc-siemens/server.cer",
        "is_file": lambda path: exists,
        "parse_certificate": lambda path: certificate,
        "materialize_pem": lambda host, received_certificate: calls.append(
            ("materialize", received_certificate, host)
        ),
        "certificate_metadata": lambda received_certificate, trust_ref: {
            "configured": True,
            "status": "ready",
            "trustRef": trust_ref,
            "fingerprintSha256": "A" * 64,
        },
        "read_metadata": lambda host: persisted,
        "validate_certificate": validate,
        "format_datetime": lambda value: "2026-09-12T10:11:12Z",
        "now": lambda: datetime(2026, 9, 12, 10, 11, 12, tzinfo=timezone.utc),
        "calls": calls,
        "certificate": certificate,
    }


def test_inspect_returns_missing_without_loading_a_certificate():
    dependencies = _dependencies(exists=False)
    dependencies["parse_certificate"] = lambda path: pytest.fail("certificate should not be parsed")

    result = winrm_trust_service.inspect_winrm_trust(
        {"name": "PC-Siemens", "address": "192.168.1.50"},
        **{key: value for key, value in dependencies.items() if key not in {"calls", "certificate"}},
    )

    assert result == {
        "configured": False,
        "status": "missing",
        "errorCode": "WINRM_TRUST_REQUIRED",
        "trustRef": "pc-siemens",
    }


def test_inspect_rejects_persisted_metadata_for_a_different_certificate():
    dependencies = _dependencies(
        persisted={"fingerprintSha256": "B" * 64},
    )
    dependencies["validate_certificate"] = lambda certificate, host: pytest.fail(
        "mismatched metadata should stop validation"
    )

    result = winrm_trust_service.inspect_winrm_trust(
        {"name": "PC-Siemens", "address": "192.168.1.50"},
        **{key: value for key, value in dependencies.items() if key not in {"calls", "certificate"}},
    )

    assert result == {
        "configured": True,
        "status": "invalid",
        "errorCode": "WINRM_TRUST_INVALID",
        "trustRef": "pc-siemens",
    }


def test_inspect_preserves_expired_status_and_persisted_upload_metadata():
    dependencies = _dependencies(
        persisted={
            "fingerprintSha256": "A" * 64,
            "uploadedAt": "2026-09-12T09:00:00Z",
            "uploadedBy": "lab-manager",
            "source": "lab-manager",
            "format": "DER",
        },
        validation_error=errors.WinRMTrustError(
            "WINRM_CERTIFICATE_EXPIRED", "WinRM certificate is expired"
        ),
    )

    result = winrm_trust_service.inspect_winrm_trust(
        {"name": "PC-Siemens", "address": "192.168.1.50"},
        **{key: value for key, value in dependencies.items() if key not in {"calls", "certificate"}},
    )

    assert result["status"] == "expired"
    assert result["errorCode"] == "WINRM_CERTIFICATE_EXPIRED"
    assert result["host"] == "PC-Siemens"
    assert result["address"] == "192.168.1.50"
    assert result["lastValidatedAt"] == "2026-09-12T10:11:12Z"
    assert result["uploadedBy"] == "lab-manager"
    assert dependencies["calls"][0][0] == "materialize"


def test_load_maps_trust_states_to_the_existing_error_contract():
    def load(state):
        return winrm_trust_service.load_winrm_trust(
            {"name": "PC-Siemens"},
            inspect_trust=lambda host: state,
            pem_path_for_host=lambda host: "/trust/pc-siemens/server.pem",
        )

    assert load({"configured": True, "status": "ready"}) == (
        "/trust/pc-siemens/server.pem",
        {"configured": True, "status": "ready"},
    )
    with pytest.raises(errors.WinRMTrustError) as missing:
        load({"configured": False, "status": "missing"})
    assert missing.value.code == "WINRM_TRUST_REQUIRED"
    with pytest.raises(errors.WinRMTrustError) as expired:
        load({"configured": True, "status": "expired"})
    assert expired.value.code == "WINRM_CERTIFICATE_EXPIRED"
    with pytest.raises(errors.WinRMTrustError) as invalid:
        load({"configured": True, "status": "invalid", "errorCode": "WINRM_TRUST_INVALID"})
    assert invalid.value.code == "WINRM_TRUST_INVALID"


def test_refresh_creates_host_directories_and_preserves_states(tmp_path):
    hosts = [
        {"name": "PC-Siemens", "winrm_trust_ref": "pc-siemens"},
        {"name": "PC-Otra", "winrm_trust_ref": "pc-otra"},
    ]
    states = {
        "PC-Siemens": {"configured": True, "status": "ready", "fingerprintSha256": "A" * 64},
        "PC-Otra": {"configured": False, "status": "missing", "errorCode": "WINRM_TRUST_REQUIRED"},
    }

    result = winrm_trust_service.refresh_winrm_trust_store(
        hosts,
        str(tmp_path),
        trust_ref_for_host=lambda host: host["winrm_trust_ref"],
        inspect_trust=lambda host: states[host["name"]],
        sanitize_log_value=lambda value: str(value),
    )

    assert result == states
    assert (tmp_path / "pc-siemens").is_dir()
    assert (tmp_path / "pc-otra").is_dir()
