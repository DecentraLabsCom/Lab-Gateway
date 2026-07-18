import json
import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

import rotate_secrets
from rotate_secrets import rotate_credentials


def _store(path: Path, key: bytes) -> None:
    token = Fernet(key).encrypt(
        json.dumps({"user": "station-user", "password": "station-password"}).encode()
    ).decode()
    path.write_text(json.dumps({"credentials": {"station-01": {"token": token}}}) + "\n")


def test_rotation_reencrypts_all_entries_and_keeps_private_backup(tmp_path, monkeypatch):
    monkeypatch.delenv("OPS_SECRETS_KEY", raising=False)
    old_key = Fernet.generate_key()
    old_key_file = tmp_path / "ops-secrets.key"
    old_key_file.write_bytes(old_key + b"\n")
    credentials_file = tmp_path / "winrm-credentials.json"
    _store(credentials_file, old_key)
    new_key_file = tmp_path / "ops-secrets.next.key"
    backup_dir = tmp_path / "backups" / "rotation-1"

    count = rotate_credentials(credentials_file, old_key_file, new_key_file, backup_dir)

    assert count == 1
    new_key = new_key_file.read_bytes().strip()
    encrypted = json.loads(credentials_file.read_text())["credentials"]["station-01"]["token"]
    assert Fernet(new_key).decrypt(encrypted.encode())
    with pytest.raises(InvalidToken):
        Fernet(old_key).decrypt(encrypted.encode())
    assert (backup_dir / credentials_file.name).exists()
    assert (backup_dir / old_key_file.name).exists()
    if os.name != "nt":
        assert os.stat(credentials_file).st_mode & 0o077 == 0
        assert os.stat(new_key_file).st_mode & 0o077 == 0


def test_rotation_rejects_corrupt_entry_without_mutating_files(tmp_path, monkeypatch):
    monkeypatch.delenv("OPS_SECRETS_KEY", raising=False)
    old_key = Fernet.generate_key()
    old_key_file = tmp_path / "ops-secrets.key"
    old_key_file.write_bytes(old_key)
    credentials_file = tmp_path / "winrm-credentials.json"
    credentials_file.write_text(json.dumps({"credentials": {"broken": {"token": "not-fernet"}}}))
    before = credentials_file.read_bytes()
    new_key_file = tmp_path / "ops-secrets.next.key"

    with pytest.raises(RuntimeError, match="No se pudo descifrar"):
        rotate_credentials(
            credentials_file,
            old_key_file,
            new_key_file,
            tmp_path / "backups" / "rotation-2",
        )

    assert credentials_file.read_bytes() == before
    assert not new_key_file.exists()


def test_main_returns_error_status_if_parser_error_hook_returns(tmp_path, monkeypatch):
    def fail_rotation(*_args):
        raise RuntimeError("rotation failed")

    monkeypatch.setattr(rotate_secrets, "rotate_credentials", fail_rotation)
    monkeypatch.setattr(rotate_secrets.argparse.ArgumentParser, "error", lambda _self, _message: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rotate_secrets",
            "--credentials-file",
            str(tmp_path / "credentials.json"),
            "--old-key-file",
            str(tmp_path / "old.key"),
            "--new-key-file",
            str(tmp_path / "new.key"),
        ],
    )

    assert rotate_secrets.main() == 2
