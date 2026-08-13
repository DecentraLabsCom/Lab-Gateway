"""Encrypted credential store for provider-local power devices."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Mapping

from cryptography.fernet import Fernet, InvalidToken


class PowerCredentialError(RuntimeError):
    """Raised when a referenced power credential cannot be resolved."""


class PowerCredentialValidationError(PowerCredentialError):
    """Raised when an administrative credential payload is invalid."""


class PowerCredentialAlreadyExistsError(PowerCredentialError):
    """Raised when an existing credential would be overwritten implicitly."""


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise PowerCredentialError("power credential store permissions could not be secured") from exc


LOGGER = logging.getLogger(__name__)

SUPPORTED_POWER_CREDENTIAL_TYPES = frozenset(
    {"snmpv1", "snmpv2c", "snmpv3", "netio-http-basic"}
)
SNMP_AUTH_PROTOCOLS = frozenset({"NONE", "MD5", "SHA", "SHA224", "SHA256", "SHA384", "SHA512"})
SNMP_PRIV_PROTOCOLS = frozenset({"NONE", "DES", "AES", "AES128"})
_REFERENCE_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


def _text(value: Any, field_name: str, *, required: bool = True, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise PowerCredentialValidationError(f"{field_name} is required")
    if len(text) > maximum:
        raise PowerCredentialValidationError(f"{field_name} is too long")
    return text


def validate_power_credential(
    credential_type: str,
    value: Mapping[str, Any],
) -> tuple[str, Dict[str, Any]]:
    """Validate and normalize the supported energy credential formats."""
    kind = str(credential_type or "").strip().lower()
    if kind not in SUPPORTED_POWER_CREDENTIAL_TYPES:
        raise PowerCredentialValidationError("credential type is unsupported")
    if not isinstance(value, Mapping) or not value:
        raise PowerCredentialValidationError("credential payload must be a non-empty object")

    payload = dict(value)
    if kind in {"snmpv1", "snmpv2c"}:
        if set(payload) - {"version", "community"}:
            raise PowerCredentialValidationError("SNMP credential contains unsupported fields")
        version = str(payload.get("version") or kind.removeprefix("snmp")).strip().lower()
        if version != kind.removeprefix("snmp"):
            raise PowerCredentialValidationError("SNMP version does not match credential type")
        return kind, {
            "version": version,
            "community": _text(payload.get("community"), "community", maximum=256),
        }

    if kind == "snmpv3":
        allowed = {
            "version",
            "username",
            "securityName",
            "authProtocol",
            "authPassword",
            "privProtocol",
            "privPassword",
            "contextName",
        }
        if set(payload) - allowed:
            raise PowerCredentialValidationError("SNMPv3 credential contains unsupported fields")
        if str(payload.get("version") or "v3").strip().lower() != "v3":
            raise PowerCredentialValidationError("SNMPv3 credential must use version v3")
        username = _text(payload.get("username") or payload.get("securityName"), "username", maximum=256)
        auth_protocol = str(payload.get("authProtocol") or "NONE").strip().upper()
        priv_protocol = str(payload.get("privProtocol") or "NONE").strip().upper()
        if auth_protocol not in SNMP_AUTH_PROTOCOLS:
            raise PowerCredentialValidationError("SNMPv3 authentication protocol is invalid")
        if priv_protocol not in SNMP_PRIV_PROTOCOLS:
            raise PowerCredentialValidationError("SNMPv3 privacy protocol is invalid")
        if priv_protocol != "NONE" and auth_protocol == "NONE":
            raise PowerCredentialValidationError("SNMPv3 privacy requires authentication")
        normalized: Dict[str, Any] = {
            "version": "v3",
            "username": username,
            "authProtocol": auth_protocol,
            "privProtocol": priv_protocol,
        }
        if auth_protocol != "NONE":
            normalized["authPassword"] = _text(
                payload.get("authPassword"), "authentication password", maximum=512
            )
        if priv_protocol != "NONE":
            normalized["privPassword"] = _text(
                payload.get("privPassword"), "privacy password", maximum=512
            )
        context_name = _text(payload.get("contextName"), "context name", required=False, maximum=256)
        if context_name:
            normalized["contextName"] = context_name
        return kind, normalized

    if set(payload) - {"username", "password"}:
        raise PowerCredentialValidationError("NETIO credential contains unsupported fields")
    return kind, {
        "username": _text(payload.get("username"), "username", maximum=256),
        "password": _text(payload.get("password"), "password", maximum=512),
    }


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
        self._lock = RLock()

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
            raise PowerCredentialValidationError("power credentialRef is required")
        if not _REFERENCE_RE.fullmatch(reference):
            raise PowerCredentialValidationError("power credentialRef is invalid")
        return reference

    def get(self, credential_ref: str) -> Mapping[str, Any]:
        reference = self._reference(credential_ref)
        with self._lock:
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
        with self._lock:
            data = self._read_store(allow_missing=True)
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
        kind, validated_value = validate_power_credential(credential_type, value)
        try:
            payload = json.dumps(validated_value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PowerCredentialValidationError("power credential payload is not JSON serializable") from exc

        with self._lock:
            token = self._fernet_instance().encrypt(payload).decode("ascii")
            data = self._read_store(allow_missing=True)
            credentials = data["credentials"]
            if reference in credentials and not overwrite:
                raise PowerCredentialAlreadyExistsError("power credential reference already exists")
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
                _secure_file(temporary)
                os.replace(temporary, self.path)
                temporary = None
                _secure_file(self.path)
            except OSError as exc:
                raise PowerCredentialError("power credential store could not be written") from exc
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink()
                    except OSError:
                        LOGGER.warning("Unable to remove temporary power credential store file")
        return {"credentialRef": reference, "type": kind}
