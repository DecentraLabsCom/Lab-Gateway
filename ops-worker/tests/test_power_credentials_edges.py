import json
import os
import sys

import pytest
from cryptography.fernet import Fernet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power import credentials as credentials_module
from power.credentials import (
    PowerCredentialError,
    PowerCredentialValidationError,
    PowerCredentialStore,
    validate_power_credential,
)


def test_validate_snmpv3_normalizes_security_and_privacy_fields():
    kind, value = validate_power_credential(
        "SNMPV3",
        {
            "securityName": "  monitor ",
            "authProtocol": "sha256",
            "authPassword": "auth-secret",
            "privProtocol": "aes128",
            "privPassword": "privacy-secret",
            "contextName": " lab ",
        },
    )

    assert kind == "snmpv3"
    assert value == {
        "version": "v3",
        "username": "monitor",
        "authProtocol": "SHA256",
        "authPassword": "auth-secret",
        "privProtocol": "AES128",
        "privPassword": "privacy-secret",
        "contextName": "lab",
    }


@pytest.mark.parametrize(
    ("credential_type", "value", "message"),
    [
        ("unknown", {"value": "x"}, "unsupported"),
        ("snmpv2c", {}, "non-empty object"),
        ("snmpv2c", {"version": "v1", "community": "private"}, "does not match"),
        ("snmpv2c", {"community": "private", "extra": "x"}, "unsupported fields"),
        ("snmpv3", {"username": "user", "extra": "x"}, "unsupported fields"),
        ("snmpv3", {"version": "v2c", "username": "user"}, "version v3"),
        ("snmpv3", {"username": "user", "authProtocol": "bogus"}, "authentication protocol"),
        ("snmpv3", {"username": "user", "privProtocol": "DES"}, "requires authentication"),
        ("netio-http-basic", {"username": "user", "password": "p", "extra": "x"}, "unsupported fields"),
    ],
)
def test_validate_power_credential_rejects_unsafe_shapes(credential_type, value, message):
    with pytest.raises(PowerCredentialValidationError, match=message):
        validate_power_credential(credential_type, value)


def test_validate_power_credential_rejects_missing_and_oversized_secret_fields():
    with pytest.raises(PowerCredentialValidationError, match="community is required"):
        validate_power_credential("snmpv2c", {"community": ""})

    with pytest.raises(PowerCredentialValidationError, match="password is too long"):
        validate_power_credential(
            "netio-http-basic",
            {"username": "user", "password": "x" * 513},
        )

    with pytest.raises(PowerCredentialValidationError, match="authentication password"):
        validate_power_credential(
            "snmpv3",
            {"username": "user", "authProtocol": "SHA"},
        )


def test_store_reads_secret_key_from_file_and_reports_store_errors(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    key_file = tmp_path / "secrets-key"
    key_file.write_text(f"  {key}\n", encoding="utf-8")
    monkeypatch.delenv("OPS_SECRETS_KEY", raising=False)
    monkeypatch.setenv("OPS_SECRETS_KEY_FILE", str(key_file))
    monkeypatch.setenv("OPS_POWER_CREDENTIALS_PATH", str(tmp_path / "store.json"))

    store = PowerCredentialStore.from_environment()
    assert store.list() == []

    with pytest.raises(PowerCredentialValidationError, match="credentialRef is required"):
        store.get("")


def test_store_rejects_invalid_references_and_malformed_payloads(tmp_path):
    store = PowerCredentialStore(str(tmp_path / "store.json"), Fernet.generate_key().decode("ascii"))

    with pytest.raises(PowerCredentialValidationError, match="credentialRef is invalid"):
        store.put("../secret", "snmpv2c", {"community": "private"})

    (tmp_path / "store.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(PowerCredentialError, match="store is unavailable"):
        store.list()

    (tmp_path / "store.json").write_text(json.dumps({"credentials": {"pdu": {}}}), encoding="utf-8")
    with pytest.raises(PowerCredentialError, match="store is invalid"):
        store.list()


def test_store_rejects_missing_reference_and_bad_ciphertext(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    path = tmp_path / "store.json"
    store = PowerCredentialStore(str(path), key)

    path.write_text(json.dumps({"credentials": {}}), encoding="utf-8")
    with pytest.raises(PowerCredentialError, match="reference is not configured"):
        store.get("pdu")

    path.write_text(
        json.dumps({"credentials": {"pdu": {"type": "snmpv2c", "token": "bad"}}}),
        encoding="utf-8",
    )
    with pytest.raises(PowerCredentialError, match="could not be decrypted"):
        store.get("pdu")


def test_store_rejects_invalid_decrypted_payload(tmp_path):
    key = Fernet.generate_key()
    token = Fernet(key).encrypt(json.dumps(["not", "an", "object"]).encode()).decode("ascii")
    path = tmp_path / "store.json"
    path.write_text(json.dumps({"credentials": {"pdu": {"token": token}}}), encoding="utf-8")

    with pytest.raises(PowerCredentialError, match="payload is invalid"):
        PowerCredentialStore(str(path), key.decode("ascii")).get("pdu")


def test_secure_file_error_is_translated(monkeypatch, tmp_path):
    path = tmp_path / "credential-store"

    def fail_chmod(*_args):
        raise OSError("permission denied")

    monkeypatch.setattr(credentials_module.os, "chmod", fail_chmod)
    with pytest.raises(PowerCredentialError, match="permissions could not be secured"):
        credentials_module._secure_file(path)
