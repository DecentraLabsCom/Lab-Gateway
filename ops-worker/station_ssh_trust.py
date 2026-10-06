"""Per-host SSH host-key preview, explicit confirmation, and strict pin lookup."""

import base64
import hashlib
import hmac
import json
import os
import re
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

import paramiko

from station_errors import StationTrustMismatch, StationTrustRequired, StationUnreachable


_REF = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def _trust_ref(host: Mapping[str, Any]) -> str:
    management = host.get("management") if isinstance(host.get("management"), Mapping) else {}
    ref = str(management.get("trustRef") or host.get("ssh_trust_ref") or host.get("name") or host.get("address") or "").strip().lower()
    if not _REF.fullmatch(ref) or ".." in ref:
        raise ValueError("station trust reference is invalid")
    return ref


def _root() -> str:
    return os.getenv("OPS_STATION_TRUST_PATH", "/app/data/station-trust")


def _paths(host: Mapping[str, Any]) -> Tuple[str, str]:
    root = os.path.realpath(os.path.abspath(_root()))
    ref = _trust_ref(host)
    directory = os.path.realpath(os.path.join(root, "ssh", ref))
    if os.path.commonpath((root, directory)) != root:
        raise ValueError("station trust reference is invalid")
    return os.path.join(directory, "known_host"), os.path.join(directory, "metadata.json")


def _fingerprint(key: paramiko.PKey) -> str:
    encoded = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def _address_port(host: Mapping[str, Any]) -> Tuple[str, int]:
    management = host.get("management") if isinstance(host.get("management"), Mapping) else {}
    address = str(host.get("address") or "").strip()
    try:
        port = int(management.get("port") or host.get("management_port") or 22)
    except (TypeError, ValueError) as exc:
        raise ValueError("SSH management port is invalid") from exc
    if not address or port < 1 or port > 65535:
        raise ValueError("SSH management endpoint is invalid")
    return address, port


def probe_ssh_host_key(host: Mapping[str, Any], *, timeout: float = 5.0) -> Dict[str, str]:
    """Read a public host key for operator preview only; never persist it here."""
    address, port = _address_port(host)
    sock = None
    transport = None
    try:
        sock = socket.create_connection((address, port), timeout=timeout)
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        if key.get_name() != "ssh-ed25519":
            raise StationTrustMismatch("Only Ed25519 SSH host keys are accepted")
        return {"algorithm": key.get_name(), "keyData": key.get_base64(), "fingerprint": _fingerprint(key)}
    except StationTrustMismatch:
        raise
    except (OSError, socket.timeout, paramiko.SSHException) as exc:
        raise StationUnreachable() from exc
    finally:
        if transport:
            transport.close()
        elif sock:
            sock.close()


def confirm_ssh_host_key(host: Mapping[str, Any], fingerprint: str, *, timeout: float = 5.0) -> Dict[str, Any]:
    """Re-probe and persist a host key only when its displayed SHA-256 was confirmed."""
    preview = probe_ssh_host_key(host, timeout=timeout)
    if not fingerprint or not hmac.compare_digest(fingerprint, preview["fingerprint"]):
        raise StationTrustMismatch("The confirmed SSH fingerprint does not match the current host key")
    known_path, metadata_path = _paths(host)
    os.makedirs(os.path.dirname(known_path), mode=0o700, exist_ok=True)
    address, port = _address_port(host)
    known_host = address if port == 22 else f"[{address}]:{port}"
    encoded_line = f"{known_host} {preview['algorithm']} {preview['keyData']}\n"
    metadata = {
        "host": str(host.get("name") or address),
        "address": address,
        "port": port,
        "algorithm": preview["algorithm"],
        "fingerprint": preview["fingerprint"],
        "confirmedAt": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(known_path, encoded_line.encode("ascii"), 0o600)
    _atomic_write(metadata_path, (json.dumps(metadata, indent=2) + "\n").encode("utf-8"), 0o600)
    return metadata


def _atomic_write(path: str, value: bytes, mode: int) -> None:
    temporary = f"{path}.tmp-{os.getpid()}"
    try:
        with open(temporary, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def load_confirmed_ssh_host_key(host: Mapping[str, Any]) -> Tuple[str, str, str]:
    """Return the expected algorithm, base64 key, and fingerprint for one host."""
    known_path, metadata_path = _paths(host)
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        with open(known_path, "r", encoding="ascii") as handle:
            line = handle.readline().strip().split()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise StationTrustRequired() from exc
    if len(line) != 3 or line[1] != "ssh-ed25519":
        raise StationTrustRequired("A confirmed Ed25519 SSH host key is required")
    address, port = _address_port(host)
    expected_name = address if port == 22 else f"[{address}]:{port}"
    if line[0] != expected_name or metadata.get("address") != address or int(metadata.get("port", 0)) != port:
        raise StationTrustMismatch("SSH trust entry belongs to a different station or port")
    key_data = base64.b64decode(line[2], validate=True)
    actual = paramiko.PKey.from_type_string(line[1], key_data)
    if _fingerprint(actual) != metadata.get("fingerprint"):
        raise StationTrustMismatch()
    return line[1], line[2], str(metadata["fingerprint"])


def ssh_trust_status(host: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        algorithm, _, fingerprint = load_confirmed_ssh_host_key(host)
        return {"status": "ready", "algorithm": algorithm, "fingerprint": fingerprint}
    except StationTrustMismatch:
        return {"status": "mismatch", "algorithm": "ssh-ed25519", "fingerprint": None}
    except StationTrustRequired:
        return {"status": "missing", "algorithm": None, "fingerprint": None}


def delete_ssh_trust(host: Mapping[str, Any]) -> bool:
    paths = _paths(host)
    removed = False
    for path in paths:
        try:
            os.remove(path)
            removed = True
        except FileNotFoundError:
            continue
    return removed


__all__ = ["probe_ssh_host_key", "confirm_ssh_host_key", "load_confirmed_ssh_host_key", "ssh_trust_status", "delete_ssh_trust"]
