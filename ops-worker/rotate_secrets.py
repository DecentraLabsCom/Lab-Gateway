#!/usr/bin/env python3
"""Rotate the Fernet key used by the encrypted WinRM credential store.

The command validates every credential before changing either file.  It keeps
an operator-readable backup beside the credential store and never prints
credential material or encryption keys.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        handle.write(content)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows ACLs are the effective control on Windows bind mounts.
        pass
    _harden_windows_file(path)


def _harden_windows_file(path: Path) -> None:
    """Remove inherited ACLs when rotation is run on a Windows host."""
    if os.name != "nt":
        return
    username = os.environ.get("USERNAME", "").strip()
    if not username:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        # Surface the path in the operator output; do not fail rotation after
        # the encrypted files have already been atomically written.
        pass


def _load_key_from_environment() -> str:
    key = os.getenv("OPS_SECRETS_KEY", "").strip()
    if key:
        return key
    file_path = os.getenv("OPS_SECRETS_KEY_FILE", "").strip()
    if file_path:
        candidate = Path(file_path)
        if candidate.is_file():
            return _read_text(candidate)
    return ""


def _load_old_key(old_key_file: Path) -> bytes:
    key = _load_key_from_environment()
    if not key and old_key_file.is_file():
        key = _read_text(old_key_file)
    if not key:
        raise RuntimeError(
            f"No se encontró la clave actual; configura OPS_SECRETS_KEY o usa {old_key_file}"
        )
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("La clave actual no tiene formato Fernet válido") from exc
    return key.encode("ascii")


def _load_new_key(new_key_file: Path) -> bytes:
    if new_key_file.exists():
        key = _read_text(new_key_file)
    else:
        key = Fernet.generate_key().decode("ascii")
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("La nueva clave no tiene formato Fernet válido") from exc
    return key.encode("ascii")


def _backup_files(
    credentials_file: Path,
    old_key_file: Path,
    backup_dir: Path,
) -> None:
    backup_dir.mkdir(parents=True, exist_ok=False)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        # Permission hardening is best effort on filesystems without POSIX modes.
        pass
    _harden_windows_file(backup_dir)
    for source in (credentials_file, old_key_file):
        if not source.is_file():
            continue
        target = backup_dir / source.name
        shutil.copy2(source, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            # Permission hardening is best effort on filesystems without POSIX modes.
            pass
        _harden_windows_file(target)


def rotate_credentials(
    credentials_file: Path,
    old_key_file: Path,
    new_key_file: Path,
    backup_dir: Path,
) -> int:
    """Re-encrypt all entries and atomically replace the two active files."""
    if not credentials_file.is_file():
        raise RuntimeError(f"No existe el almacén de credenciales: {credentials_file}")

    try:
        store = json.loads(credentials_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer el almacén de credenciales: {credentials_file}") from exc
    if not isinstance(store, dict) or not isinstance(store.get("credentials"), dict):
        raise RuntimeError("El almacén no contiene un objeto 'credentials' válido")

    old_fernet = Fernet(_load_old_key(old_key_file))
    new_key = _load_new_key(new_key_file)
    new_fernet = Fernet(new_key)
    rotated: Dict[str, Any] = {}

    # Validate and transform everything before creating the backup or changing
    # active files. A bad entry therefore cannot leave a partially rotated store.
    for reference, entry in store["credentials"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("token"), str):
            raise RuntimeError(f"Entrada inválida para credential_ref {reference!r}")
        try:
            cleartext = old_fernet.decrypt(entry["token"].encode("ascii"))
            payload = json.loads(cleartext.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"No se pudo descifrar credential_ref {reference!r}") from exc
        if not isinstance(payload, dict) or not payload.get("user") or not payload.get("password"):
            raise RuntimeError(f"Contenido inválido para credential_ref {reference!r}")
        rotated[reference] = {
            **entry,
            "token": new_fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii"),
        }

    backup_dir.parent.mkdir(parents=True, exist_ok=True)
    _backup_files(credentials_file, old_key_file, backup_dir)

    updated = {**store, "credentials": rotated}
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=credentials_file.parent,
        prefix=f".{credentials_file.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_credentials = Path(handle.name)
        os.chmod(temporary_credentials, 0o600)
        json.dump(updated, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_credentials, credentials_file)
    try:
        os.chmod(credentials_file, 0o600)
    except OSError:
        # Permission hardening is best effort on filesystems without POSIX modes.
        pass
    _harden_windows_file(credentials_file)

    _write_private(new_key_file, new_key.decode("ascii"))
    return len(rotated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--old-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--new-key-file",
        type=Path,
        required=True,
        help="Ruta de la nueva clave; se genera si todavía no existe",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directorio vacío para la copia de seguridad; por defecto se crea junto al almacén",
    )
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = args.backup_dir or args.credentials_file.parent / "backups" / f"ops-secrets-{timestamp}"
    try:
        count = rotate_credentials(
            args.credentials_file,
            args.old_key_file,
            args.new_key_file,
            backup_dir,
        )
    except (OSError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2
    print(f"Rotadas {count} credenciales; copia de seguridad: {backup_dir}")
    print(f"Nueva clave escrita en: {args.new_key_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
