"""Encrypted credential store for provider-local power devices."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from cryptography.fernet import Fernet, InvalidToken


class PowerCredentialError(RuntimeError):
    """Raised when a referenced power credential cannot be resolved."""


def _secret_value(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if value:
        return value
    file_path = str(os.getenv(f"{name}_FILE") or "").strip()
    if not file_path:
        return ""
    try:
        return Path(file_path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PowerCredentialError("power credential key is unavailable") from exc


class PowerCredentialStore:
    """Manage encrypted JSON credentials by reference without exposing them."""

    def __init__(self, path: str, key: str) -> None:
        self.path = Path(path)
        self._key = str(key or "")
        self._fernet = None

    @classmethod
    def from_environment(cls) -> "PowerCredentialStore":
        path = os.getenv("OPS_POWER_CREDENTIALS_PATH", "/app/data/power-credentials.json")
        return cls(path, _secret_value("OPS_SECRETS_KEY"))

    def _fernet_instance(self) -> Fernet:
        if not self._key:
            raise PowerCredentialError("power credential encryption key is unavailable")
        if self._fernet is None:
            try:
                self._fernet = Fernet(self._key.encode("ascii"))
            except (ValueError, UnicodeEncodeError) as exc:
                raise PowerCredentialError("power credential encryption key is invalid") from exc
        return self._fernet

    def _read_store(self, *, allow_missing: bool = False) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if allow_missing:
                return {"credentials": {}}
            raise PowerCredentialError("power credential store is unavailable")
        except (OSError, json.JSONDecodeError) as exc:
            raise PowerCredentialError("power credential store is unavailable") from exc
        if not isinstance(data, dict) or not isinstance(data.get("credentials"), dict):
            raise PowerCredentialError("power credential store is invalid")
        return data

    @staticmethod
    def _reference(credential_ref: str) -> str:
        reference = str(credential_ref or "").strip().lower()
        if not reference:
            raise PowerCredentialError("power credentialRef is required")
        if len(reference) > 128:
            raise PowerCredentialError("power credentialRef is too long")
        return reference

    def get(self, credential_ref: str) -> Mapping[str, Any]:
        reference = self._reference(credential_ref)
        fernet = self._fernet_instance()
        data = self._read_store()
        entry = data["credentials"].get(reference)
        if not isinstance(entry, Mapping) or not str(entry.get("token") or "").strip():
            raise PowerCredentialError("power credential reference is not configured")
        try:
            raw = fernet.decrypt(str(entry["token"]).encode("ascii"))
            value = json.loads(raw.decode("utf-8"))
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PowerCredentialError("power credential could not be decrypted") from exc
        if not isinstance(value, Mapping):
            raise PowerCredentialError("power credential payload is invalid")
        return dict(value)

    def list(self) -> list[Dict[str, str]]:
        """Return credential metadata only; encrypted payloads never leave the store."""
        data = self._read_store()
        result = []
        for reference, entry in data["credentials"].items():
            if not isinstance(entry, Mapping) or not str(entry.get("token") or "").strip():
                raise PowerCredentialError("power credential store is invalid")
            result.append(
                {
                    "credentialRef": str(reference),
                    "type": str(entry.get("type") or "unknown"),
                }
            )
        return sorted(result, key=lambda item: item["credentialRef"])

    def put(
        self,
        credential_ref: str,
        credential_type: str,
        value: Mapping[str, Any],
        *,
        overwrite: bool = False,
    ) -> Dict[str, str]:
        """Encrypt and atomically save one credential, returning metadata only."""
        reference = self._reference(credential_ref)
        kind = str(credential_type or "").strip().lower()
        if not kind:
            raise PowerCredentialError("power credential type is required")
        if len(kind) > 64:
            raise PowerCredentialError("power credential type is too long")
        if not isinstance(value, Mapping) or not value:
            raise PowerCredentialError("power credential payload must be a non-empty object")

        try:
            payload = json.dumps(dict(value), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PowerCredentialError("power credential payload is not JSON serializable") from exc
        token = self._fernet_instance().encrypt(payload).decode("ascii")
        data = self._read_store(allow_missing=True)
        credentials = data["credentials"]
        if reference in credentials and not overwrite:
            raise PowerCredentialError("power credential reference already exists")
        credentials[reference] = {"type": kind, "token": token}

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
            temporary = None
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            raise PowerCredentialError("power credential store could not be written") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass
        return {"credentialRef": reference, "type": kind}
