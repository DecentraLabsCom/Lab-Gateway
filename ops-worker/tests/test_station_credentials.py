import json

import pytest
from cryptography.fernet import Fernet

import station_credentials as credentials


@pytest.fixture
def credential_store(tmp_path, monkeypatch):
    path = tmp_path / "station-credentials.json"
    monkeypatch.setenv("OPS_STATION_CREDENTIALS_PATH", str(path))
    monkeypatch.setenv("OPS_SECRETS_KEY", Fernet.generate_key().decode("ascii"))
    return path


def test_ssh_credential_round_trip_keeps_private_key_encrypted_and_private(credential_store):
    public = credentials.generate_ssh_credential("Station-Linux_1")
    persisted = json.loads(credential_store.read_text(encoding="utf-8"))
    stored = persisted["credentials"]["station-linux_1"]

    assert public["type"] == "ssh-ed25519"
    assert public["username"] == "labstation-ops"
    assert public["publicKey"].startswith("ssh-ed25519 ")
    assert "privateKey" not in public
    assert "PRIVATE KEY" not in credential_store.read_text(encoding="utf-8")
    assert stored["token"] != public["publicKey"]
    assert credentials.load_ssh_credential("station-linux_1")["privateKey"].startswith("-----BEGIN OPENSSH PRIVATE KEY-----")


def test_public_credential_never_returns_the_private_half(credential_store):
    credentials.generate_ssh_credential("station-2")

    public = credentials.public_ssh_credential("station-2")

    assert set(public) == {"credentialRef", "username", "publicKey", "type"}
    assert public["credentialRef"] == "station-2"


@pytest.mark.parametrize("credential_ref", ["../root", "a/b", "..", "UPPER/unsafe", "x" * 129, ""])
def test_credential_reference_rejects_path_and_length_traversal(credential_ref):
    with pytest.raises(ValueError):
        credentials.normalize_credential_ref(credential_ref)


@pytest.mark.parametrize("username", ["root", "lab user", "-option", "x" * 65, ""])
def test_credential_generation_rejects_unsafe_usernames(credential_store, username):
    with pytest.raises(ValueError, match="username"):
        credentials.generate_ssh_credential("station-3", username=username)


def test_secret_key_is_required_and_corrupt_ciphertext_fails_closed(credential_store, monkeypatch):
    monkeypatch.delenv("OPS_SECRETS_KEY")
    with pytest.raises(RuntimeError, match="OPS_SECRETS_KEY"):
        credentials.generate_ssh_credential("station-4")

    monkeypatch.setenv("OPS_SECRETS_KEY", Fernet.generate_key().decode("ascii"))
    credentials.generate_ssh_credential("station-4")
    payload = json.loads(credential_store.read_text(encoding="utf-8"))
    payload["credentials"]["station-4"]["token"] = "tampered"
    credential_store.write_text(json.dumps(payload), encoding="utf-8")

    assert credentials.load_ssh_credential("station-4") is None


def test_delete_is_idempotent_and_removes_only_the_named_reference(credential_store):
    credentials.generate_ssh_credential("station-5")
    credentials.generate_ssh_credential("station-6")

    assert credentials.delete_ssh_credential("station-5") is True
    assert credentials.delete_ssh_credential("station-5") is False
    assert credentials.load_ssh_credential("station-5") is None
    assert credentials.load_ssh_credential("station-6") is not None
