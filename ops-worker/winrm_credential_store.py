"""Encrypted persistence primitives for stored WinRM credentials."""

import json
import os
from typing import Any, Callable, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken


def load_fernet(
    cached: Optional[Fernet],
    *,
    read_secret: Callable[[str], str],
    fernet_factory: Callable[[bytes], Fernet] = Fernet,
) -> Fernet:
    """Return the cached Fernet instance or construct it from the secret key."""
    if cached:
        return cached
    key = str(read_secret("OPS_SECRETS_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPS_SECRETS_KEY is required to encrypt WinRM credentials")
    return fernet_factory(key.encode("ascii"))


def fernet_key_is_usable(*, load_fernet: Callable[[], Fernet], logger: Any) -> bool:
    """Return whether the configured Fernet key can be loaded for health checks."""
    try:
        load_fernet()
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("OPS_SECRETS_KEY is unavailable or invalid: %s", type(exc).__name__)
        return False


def encrypt_secret(value: str, *, load_fernet: Callable[[], Fernet]) -> str:
    """Encrypt one runtime secret using the configured Fernet instance."""
    return load_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, *, load_fernet: Callable[[], Fernet]) -> str:
    """Decrypt one runtime secret from its ASCII Fernet representation."""
    return load_fernet().decrypt(value.encode("ascii")).decode("utf-8")


def read_credentials_store(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"credentials": {}}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"credentials": {}}
    if not isinstance(data.get("credentials"), dict):
        data["credentials"] = {}
    return data


def write_credentials_store(path: str, data: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Permission hardening is best-effort on bind mounts and Windows filesystems.
        pass


def save_credentials(
    credential_ref: str,
    user: str,
    password: str,
    *,
    normalize_ref: Callable[[Any], str],
    load_fernet: Callable[[], Fernet],
    read_store: Callable[[], Dict[str, Any]],
    write_store: Callable[[Dict[str, Any]], None],
) -> None:
    ref = normalize_ref(credential_ref)
    if not ref:
        raise ValueError("credentialRef is required")
    if not str(user or "").strip():
        raise ValueError("user is required")
    if not str(password or "").strip():
        raise ValueError("password is required")
    token = load_fernet().encrypt(json.dumps({
        "user": str(user).strip(),
        "password": str(password),
    }).encode("utf-8")).decode("ascii")
    data = read_store()
    data["credentials"][ref] = {"token": token}
    write_store(data)


def load_credentials(
    credential_ref: str,
    *,
    normalize_ref: Callable[[Any], str],
    load_fernet: Callable[[], Fernet],
    read_store: Callable[[], Dict[str, Any]],
    logger: Any,
) -> Optional[Dict[str, str]]:
    ref = normalize_ref(credential_ref)
    if not ref:
        return None
    entry = read_store().get("credentials", {}).get(ref)
    if not isinstance(entry, dict) or not entry.get("token"):
        return None
    try:
        raw = load_fernet().decrypt(str(entry["token"]).encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Unable to decrypt WinRM credential ref %s: %s",
            str(ref).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return None
    user = str(parsed.get("user") or "").strip()
    password = str(parsed.get("password") or "")
    if not user or not password:
        return None
    return {"user": user, "password": password}


__all__ = [
    "load_fernet",
    "fernet_key_is_usable",
    "encrypt_secret",
    "decrypt_secret",
    "read_credentials_store",
    "write_credentials_store",
    "save_credentials",
    "load_credentials",
]
