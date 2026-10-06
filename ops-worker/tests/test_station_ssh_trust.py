import json

import paramiko
import pytest

import station_ssh_trust as trust
from station_errors import StationTrustMismatch, StationTrustRequired


@pytest.fixture
def trust_root(tmp_path, monkeypatch):
    root = tmp_path / "trusted-stations"
    monkeypatch.setenv("OPS_STATION_TRUST_PATH", str(root))
    return root


def _host(port=2222, name="station-linux"):
    return {"name": name, "address": "127.0.0.1", "management": {"transport": "ssh", "port": port, "trustRef": name}}


def _preview(key):
    return {"algorithm": key.get_name(), "keyData": key.get_base64(), "fingerprint": trust._fingerprint(key)}


def _new_ed25519_key():
    from io import StringIO
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    private_text = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode("ascii")
    return paramiko.Ed25519Key.from_private_key(StringIO(private_text))


def test_host_key_preview_does_not_pin_without_explicit_confirmation(trust_root, monkeypatch):
    key = _new_ed25519_key()
    preview = _preview(key)

    result = trust.probe_ssh_host_key
    monkeypatch.setattr(trust, "socket", type("Socket", (), {"create_connection": lambda *args, **kwargs: object()}))

    class FakeTransport:
        def __init__(self, sock):
            self.sock = sock

        def start_client(self, timeout):
            pass

        def get_remote_server_key(self):
            return key

        def close(self):
            pass

    monkeypatch.setattr(trust.paramiko, "Transport", FakeTransport)
    assert result(_host()) == preview
    assert list(trust_root.rglob("*")) == []


def test_confirmation_reprobes_and_persists_only_the_matching_fingerprint(trust_root, monkeypatch):
    key = _new_ed25519_key()
    preview = _preview(key)
    monkeypatch.setattr(trust, "probe_ssh_host_key", lambda host, timeout=5.0: preview)

    metadata = trust.confirm_ssh_host_key(_host(), preview["fingerprint"])

    assert metadata["address"] == "127.0.0.1"
    assert metadata["port"] == 2222
    assert metadata["fingerprint"] == preview["fingerprint"]
    assert trust.ssh_trust_status(_host())["status"] == "ready"
    known_host = next(trust_root.rglob("known_host")).read_text(encoding="ascii")
    assert known_host.startswith("[127.0.0.1]:2222 ssh-ed25519 ")
    assert trust.load_confirmed_ssh_host_key(_host()) == ("ssh-ed25519", preview["keyData"], preview["fingerprint"])


def test_confirmation_rejects_mismatched_or_empty_fingerprints_without_persisting(trust_root, monkeypatch):
    preview = _preview(_new_ed25519_key())
    monkeypatch.setattr(trust, "probe_ssh_host_key", lambda host, timeout=5.0: preview)

    for fingerprint in ("", "SHA256:wrong"):
        with pytest.raises(StationTrustMismatch):
            trust.confirm_ssh_host_key(_host(), fingerprint)
    assert list(trust_root.rglob("*")) == []


def test_trust_entry_cannot_be_replayed_for_another_address_or_ssh_port(trust_root, monkeypatch):
    preview = _preview(_new_ed25519_key())
    monkeypatch.setattr(trust, "probe_ssh_host_key", lambda host, timeout=5.0: preview)
    trust.confirm_ssh_host_key(_host(), preview["fingerprint"])

    with pytest.raises(StationTrustMismatch):
        trust.load_confirmed_ssh_host_key(_host(port=2223))
    with pytest.raises(StationTrustMismatch):
        trust.load_confirmed_ssh_host_key({**_host(), "address": "192.0.2.9"})


def test_tampered_metadata_is_detected_and_can_be_removed(trust_root, monkeypatch):
    preview = _preview(_new_ed25519_key())
    monkeypatch.setattr(trust, "probe_ssh_host_key", lambda host, timeout=5.0: preview)
    trust.confirm_ssh_host_key(_host(), preview["fingerprint"])
    metadata_path = next(trust_root.rglob("metadata.json"))
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    data["fingerprint"] = "SHA256:tampered"
    metadata_path.write_text(json.dumps(data), encoding="utf-8")

    assert trust.ssh_trust_status(_host())["status"] == "mismatch"
    with pytest.raises(StationTrustMismatch):
        trust.load_confirmed_ssh_host_key(_host())
    assert trust.delete_ssh_trust(_host()) is True
    assert trust.delete_ssh_trust(_host()) is False
    assert trust.ssh_trust_status(_host())["status"] == "missing"


@pytest.mark.parametrize("trust_ref", ["../root", "x/y", ".."])
def test_host_trust_reference_rejects_path_traversal(trust_ref, trust_root):
    with pytest.raises(ValueError, match="trust reference"):
        trust._paths({"address": "127.0.0.1", "name": "station", "management": {"trustRef": trust_ref}})


def test_unconfirmed_key_is_never_reported_ready(trust_root):
    assert trust.ssh_trust_status(_host()) == {"status": "missing", "algorithm": None, "fingerprint": None}
    with pytest.raises(StationTrustRequired):
        trust.load_confirmed_ssh_host_key(_host())
