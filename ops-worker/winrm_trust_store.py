"""Filesystem primitives for the managed WinRM trust store.

The module receives concrete paths and callbacks.  Host lookup, path policy and
HTTP handling remain in ``worker.py`` so its historical entrypoint surface is
unchanged.
"""

from collections.abc import Callable
import json
import os
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from errors import WINRM_TRUST_ERROR_MESSAGES, WinRMTrustError


def write_trust_bytes(path: str, content: bytes) -> None:
    """Write trust material through a same-directory atomic replacement."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp-{uuid4().hex}"
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            # Cleanup is best-effort; preserve the write/replace outcome.
            pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Bind mounts and Windows filesystems may not support chmod.
        pass


def read_trust_metadata(path: str) -> Optional[Dict[str, Any]]:
    """Read one metadata file, preserving the existing missing/invalid states."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_trust_metadata(
    path: str,
    metadata: Dict[str, Any],
    *,
    write_bytes: Callable[[str, bytes], None] = write_trust_bytes,
) -> None:
    """Serialize metadata as UTF-8 JSON through the supplied atomic writer."""
    content = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
    write_bytes(path, content)


def materialize_trust_pem(
    path: str,
    certificate: x509.Certificate,
    *,
    max_bytes: int,
) -> str:
    """Materialize a canonical PEM copy so Requests/OpenSSL can consume it."""
    pem_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    try:
        current = b""
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                current = handle.read(max_bytes + 1)
        if current != pem_bytes:
            tmp_path = f"{path}.tmp-{uuid4().hex}"
            try:
                with open(tmp_path, "wb") as handle:
                    handle.write(pem_bytes)
                os.replace(tmp_path, path)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    # Cleanup is best-effort after the canonical file is in place.
                    pass
            try:
                os.chmod(path, 0o600)
            except OSError:
                # Permission hardening is best-effort on bind mounts and Windows filesystems.
                pass
    except OSError as exc:
        raise WinRMTrustError(
            "WINRM_TRUST_STORAGE_UNAVAILABLE",
            WINRM_TRUST_ERROR_MESSAGES["WINRM_TRUST_STORAGE_UNAVAILABLE"],
        ) from exc
    return path


def delete_trust_files(paths: Sequence[str]) -> None:
    """Delete managed trust files idempotently, preserving storage errors."""
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise WinRMTrustError(
                "WINRM_TRUST_STORAGE_UNAVAILABLE",
                WINRM_TRUST_ERROR_MESSAGES["WINRM_TRUST_STORAGE_UNAVAILABLE"],
            ) from exc
