"""Typed, encrypted SSH service credentials for station management."""

import json
import os
import re
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from secret_values import env_or_secret_file


_REF = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def _path() -> str:
    return os.getenv("OPS_STATION_CREDENTIALS_PATH", "/app/data/station-credentials.json")


def _fernet() -> Fernet:
    key = str(env_or_secret_file("OPS_SECRETS_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPS_SECRETS_KEY is required for station credentials")
    return Fernet(key.encode("ascii"))


def normalize_credential_ref(value: Any) -> str:
    ref = str(value or "").strip().lower()
    if not _REF.fullmatch(ref) or ".." in ref:
        raise ValueError("credentialRef contains unsupported characters")
    return ref


def _read_store(path: Optional[str] = None) -> Dict[str, Any]:
    target = path or _path()
    if not os.path.isfile(target):
        return {"schemaVersion": 1, "credentials": {}}
    with open(target, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("credentials"), dict):
        raise ValueError("station credential store is malformed")
    return value


def _write_store(value: Dict[str, Any], path: Optional[str] = None) -> None:
    target = path or _path()
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = f"{target}.tmp-{os.getpid()}"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def generate_ssh_credential(credential_ref: Any, *, username: str = "labstation-ops") -> Dict[str, str]:
    """Create one Ed25519 keypair; encrypt the private half before persistence."""
    ref = normalize_credential_ref(credential_ref)
    if username != "labstation-ops":
        raise ValueError("username must be the forced-command station management account")
    private_key = Ed25519PrivateKey.generate()
    private_text = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_text = private_key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    ).decode("ascii")
    data = _read_store()
    encrypted = _fernet().encrypt(json.dumps({"privateKey": private_text}).encode("utf-8")).decode("ascii")
    data["credentials"][ref] = {
        "type": "ssh-ed25519",
        "username": username,
        "publicKey": public_text,
        "token": encrypted,
    }
    _write_store(data)
    return {"credentialRef": ref, "username": username, "publicKey": public_text, "type": "ssh-ed25519"}


def load_ssh_credential(credential_ref: Any) -> Optional[Dict[str, str]]:
    ref = normalize_credential_ref(credential_ref)
    entry = _read_store().get("credentials", {}).get(ref)
    if not isinstance(entry, dict) or entry.get("type") != "ssh-ed25519" or not entry.get("token"):
        return None
    try:
        raw = _fernet().decrypt(str(entry["token"]).encode("ascii"))
        secret = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, RuntimeError, json.JSONDecodeError):
        return None
    private_key = str(secret.get("privateKey") or "")
    username = str(entry.get("username") or "")
    if not private_key or not username:
        return None
    return {"username": username, "privateKey": private_key, "publicKey": str(entry.get("publicKey") or "")}


def public_ssh_credential(credential_ref: Any) -> Optional[Dict[str, str]]:
    """Return installable public material and metadata, never private key data."""
    ref = normalize_credential_ref(credential_ref)
    entry = _read_store().get("credentials", {}).get(ref)
    if not isinstance(entry, dict) or entry.get("type") != "ssh-ed25519":
        return None
    return {
        "credentialRef": ref,
        "username": str(entry.get("username") or "labstation-ops"),
        "publicKey": str(entry.get("publicKey") or ""),
        "type": "ssh-ed25519",
    }


def delete_ssh_credential(credential_ref: Any) -> bool:
    ref = normalize_credential_ref(credential_ref)
    data = _read_store()
    removed = data["credentials"].pop(ref, None) is not None
    if removed:
        _write_store(data)
    return removed


__all__ = ["normalize_credential_ref", "generate_ssh_credential", "load_ssh_credential", "public_ssh_credential", "delete_ssh_credential"]
