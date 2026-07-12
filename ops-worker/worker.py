#!/usr/bin/env python3
"""
Ops worker: WoL + WinRM wrapper + heartbeat poller for Lab Station hosts.
Exposes a small Flask API and optional scheduler.
"""
import json
import hmac
import hashlib
import base64
import logging
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Response, jsonify, request, stream_with_context
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import IntegrityError
from wakeonlan import send_magic_packet
import requests
import winrm
from apscheduler.schedulers.background import BackgroundScheduler
import aas_generator

APP = Flask(__name__)

CONFIG_PATH = os.getenv("OPS_CONFIG", os.path.join(os.path.dirname(__file__), "hosts.json"))
DYNAMIC_CONFIG_PATH = os.getenv("OPS_DYNAMIC_CONFIG", "/app/data/hosts.json")
OPS_CREDENTIALS_PATH = os.getenv("OPS_CREDENTIALS_PATH", "/app/data/winrm-credentials.json")
OPS_SECRETS_KEY_PATH = os.getenv("OPS_SECRETS_KEY_PATH", "/app/data/ops-secrets.key")
MYSQL_DSN = os.getenv("MYSQL_DSN")
GUACAMOLE_MYSQL_DSN = os.getenv("GUACAMOLE_MYSQL_DSN")
OPS_MYSQL_DATABASE = os.getenv("OPS_MYSQL_DATABASE") or os.getenv("BLOCKCHAIN_MYSQL_DATABASE")
GUACAMOLE_MYSQL_DATABASE = os.getenv("GUACAMOLE_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE")
MYSQL_HOSTNAME = os.getenv("MYSQL_HOSTNAME") or os.getenv("MYSQL_HOST") or "mysql"
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
GUACAMOLE_TEMP_USER_CLEANUP_ENABLED = os.getenv(
    "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED",
    "true",
).strip().lower() not in ("false", "0", "no", "off")
GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS", "300")),
)
GUACAMOLE_PROVISIONER_TOKEN = (
    os.getenv("GUACAMOLE_PROVISIONER_TOKEN") or
    os.getenv("LAB_MANAGER_TOKEN") or
    ""
)
GUACAMOLE_PROVISIONER_TOKEN_HEADER = os.getenv(
    "GUACAMOLE_PROVISIONER_TOKEN_HEADER",
    "X-Guacamole-Provisioner-Token",
)
DEFAULT_LABSTATION_EXE = r"C:\LabStation\LabStation.exe"
WINRM_READ_TIMEOUT = int(os.getenv("OPS_WINRM_READ_TIMEOUT", "30"))
WINRM_OPERATION_TIMEOUT = int(os.getenv("OPS_WINRM_OPERATION_TIMEOUT", "20"))
ALLOWED_WINRM_COMMANDS = {
    cmd.strip()
    for cmd in os.getenv(
        "OPS_ALLOWED_COMMANDS",
        "prepare-session,release-session,power,session,energy,status-json,recovery,account,service,wol,status",
    ).split(",")
    if cmd.strip()
}

TIMELINE_MAX_LIMIT = max(1, int(os.getenv("OPS_TIMELINE_MAX_OPS", "500")))
TIMELINE_DEFAULT_LIMIT = max(1, min(int(os.getenv("OPS_TIMELINE_DEFAULT_LIMIT", "100")), TIMELINE_MAX_LIMIT))
TIMELINE_PHASE_LOOKBACK = max(TIMELINE_MAX_LIMIT, int(os.getenv("OPS_TIMELINE_PHASE_LOOKBACK", "500")))
NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    os.getenv("BLOCKCHAIN_SERVICES_NOTIFICATION_URL", "http://blockchain-services:8080/billing/admin/notifications/send")
)
NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER = os.getenv("NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER", "X-Access-Token")
NOTIFICATION_SERVICE_ACCESS_TOKEN = (
    os.getenv("NOTIFICATION_SERVICE_ACCESS_TOKEN") or
    os.getenv("ADMIN_ACCESS_TOKEN")
)
NOTIFICATION_SERVICE_ENABLED = os.getenv("NOTIFICATION_SERVICE_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")
NOTIFICATION_SERVICE_RETRY_ATTEMPTS = max(0, int(os.getenv("NOTIFICATION_SERVICE_RETRY_ATTEMPTS", "3")))
NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS = max(1, int(os.getenv("NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS", "5")))
def _is_lite_gateway() -> bool:
    issuer = (os.getenv("ISSUER") or "").strip().rstrip("/")
    if not issuer:
        return False
    server_name = (os.getenv("SERVER_NAME") or "localhost").strip()
    https_port = (os.getenv("HTTPS_PORT") or "443").strip()
    local_issuer = f"https://{server_name}{'' if https_port == '443' else ':' + https_port}/auth"
    return issuer != local_issuer.rstrip("/")


ACCESS_AUDIT_URL = os.getenv("ACCESS_AUDIT_URL", "").strip()
if not ACCESS_AUDIT_URL and not _is_lite_gateway():
    ACCESS_AUDIT_URL = "http://blockchain-services:8080/access-audit/internal/session-observed"
SESSION_OBSERVER_GATEWAY_ID = os.getenv("SESSION_OBSERVER_GATEWAY_ID", "").strip()
SESSION_OBSERVER_SIGNING_SECRET = os.getenv("SESSION_OBSERVER_SIGNING_SECRET", "").strip()
SESSION_OBSERVATION_OUTBOX_ENABLED = os.getenv(
    "SESSION_OBSERVATION_OUTBOX_ENABLED", "true"
).strip().lower() not in ("false", "0", "no", "off")
SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS", "5"))
)
SESSION_OBSERVATION_OUTBOX_BATCH_SIZE = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_BATCH_SIZE", "20"))
)
SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS", "20"))
)
SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS", "5"))
)
SESSION_OBSERVATION_INGEST_TOKEN = os.getenv("SESSION_OBSERVATION_INGEST_TOKEN", "")
GUAC_ADMIN_USER = os.getenv("GUAC_ADMIN_USER", "")
GUAC_ADMIN_PASS = os.getenv("GUAC_ADMIN_PASS", "")
GUAC_API_URL = os.getenv("GUAC_API_URL", "http://guacamole:8080/guacamole/api").rstrip("/")
GUAC_REVOCATION_SPOOL_DIR = os.getenv(
    "GUAC_REVOCATION_SPOOL_DIR", "/app/data/guac-revocation-spool"
)
GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS = max(
    1, int(os.getenv("GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS", "10"))
)
GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS = max(
    1, int(os.getenv("GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS", "20"))
)
HEARTBEAT_SSE_INTERVAL_SECONDS = max(1, int(os.getenv("OPS_HEARTBEAT_SSE_INTERVAL_SECONDS", "10")))
DISCOVERY_TIMEOUT_SECONDS = max(0.2, float(os.getenv("OPS_DISCOVERY_TIMEOUT_SECONDS", "1.5")))
DISCOVERY_WINRM_PORTS = [
    int(port.strip())
    for port in os.getenv("OPS_DISCOVERY_WINRM_PORTS", "5985,5986").split(",")
    if port.strip().isdigit()
]
DISCOVERY_LABSTATION_PORTS = [
    int(port.strip())
    for port in os.getenv("OPS_DISCOVERY_LABSTATION_PORTS", "8765,8088").split(",")
    if port.strip().isdigit()
]
DISCOVERY_LABSTATION_PATHS = [
    path.strip() if path.strip().startswith("/") else f"/{path.strip()}"
    for path in os.getenv("OPS_DISCOVERY_LABSTATION_PATHS", "/labstation/health,/health").split(",")
    if path.strip()
]
DISCOVERY_HEARTBEAT_PATHS = [
    path.strip()
    for path in os.getenv(
        "OPS_DISCOVERY_HEARTBEAT_PATHS",
        r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
    ).split(",")
    if path.strip()
]
ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
HOST_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")
GUAC_SELECTOR_RE = re.compile(r"^guac:id:([1-9][0-9]*)$")
ENOUGH_DISCOVERY_SIGNALS = {"labstation-detected", "winrm-reachable"}
HOSTS_LOCK = RLock()
_FERNET: Optional[Fernet] = None


def read_hosts_config(path: str, missing_ok: bool = True) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        if not missing_ok:
            logging.warning("Config file %s not found, continuing with empty host list", path)
        return {"hosts": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"hosts": []}
    if not isinstance(data.get("hosts"), list):
        data["hosts"] = []
    return data


def merge_host_configs(base: Dict[str, Any], dynamic: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Dict[str, Any]] = {}
    for source in (base, dynamic):
        for host in source.get("hosts", []):
            if not isinstance(host, dict):
                continue
            name = str(host.get("name") or "").strip()
            if not name:
                continue
            merged[name.lower()] = dict(host)
    return {"hosts": list(merged.values())}


def _load_or_create_fernet() -> Fernet:
    global _FERNET  # pylint: disable=global-statement
    if _FERNET:
        return _FERNET
    key = os.getenv("OPS_SECRETS_KEY", "").strip()
    if not key:
        try:
            if os.path.exists(OPS_SECRETS_KEY_PATH):
                with open(OPS_SECRETS_KEY_PATH, "rb") as handle:
                    key = handle.read().decode("ascii").strip()
            else:
                os.makedirs(os.path.dirname(OPS_SECRETS_KEY_PATH) or ".", exist_ok=True)
                key = Fernet.generate_key().decode("ascii")
                with open(OPS_SECRETS_KEY_PATH, "w", encoding="ascii") as handle:
                    handle.write(key)
                    handle.write("\n")
                try:
                    os.chmod(OPS_SECRETS_KEY_PATH, 0o600)
                except OSError:
                    pass
                logging.warning("Generated local OPS_SECRETS_KEY at %s; set OPS_SECRETS_KEY explicitly for production backups", OPS_SECRETS_KEY_PATH)
        except OSError as exc:
            raise RuntimeError(f"Unable to load or create OPS_SECRETS_KEY: {exc}") from exc
    _FERNET = Fernet(key.encode("ascii"))
    return _FERNET


def normalize_credential_ref(value: Any) -> str:
    return str(value or "").strip().lower()


def credential_ref_for_host(host: Dict[str, Any]) -> str:
    return normalize_credential_ref(host.get("credential_ref") or host.get("address") or host.get("name"))


def read_winrm_credentials_store() -> Dict[str, Any]:
    if not os.path.exists(OPS_CREDENTIALS_PATH):
        return {"credentials": {}}
    with open(OPS_CREDENTIALS_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"credentials": {}}
    if not isinstance(data.get("credentials"), dict):
        data["credentials"] = {}
    return data


def write_winrm_credentials_store(data: Dict[str, Any]) -> None:
    directory = os.path.dirname(OPS_CREDENTIALS_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{OPS_CREDENTIALS_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, OPS_CREDENTIALS_PATH)
    try:
        os.chmod(OPS_CREDENTIALS_PATH, 0o600)
    except OSError:
        pass


def save_winrm_credentials(credential_ref: str, user: str, password: str) -> None:
    ref = normalize_credential_ref(credential_ref)
    if not ref:
        raise ValueError("credentialRef is required")
    if not str(user or "").strip():
        raise ValueError("user is required")
    if not str(password or "").strip():
        raise ValueError("password is required")
    token = _load_or_create_fernet().encrypt(json.dumps({
        "user": str(user).strip(),
        "password": str(password),
    }).encode("utf-8")).decode("ascii")
    data = read_winrm_credentials_store()
    data["credentials"][ref] = {"token": token}
    write_winrm_credentials_store(data)


def load_winrm_credentials(credential_ref: str) -> Optional[Dict[str, str]]:
    ref = normalize_credential_ref(credential_ref)
    if not ref:
        return None
    entry = read_winrm_credentials_store().get("credentials", {}).get(ref)
    if not isinstance(entry, dict) or not entry.get("token"):
        return None
    try:
        raw = _load_or_create_fernet().decrypt(str(entry["token"]).encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        logging.warning("Unable to decrypt WinRM credential ref %s: %s", ref, exc)
        return None
    user = str(parsed.get("user") or "").strip()
    password = str(parsed.get("password") or "")
    if not user or not password:
        return None
    return {"user": user, "password": password}


def winrm_credentials_configured(credential_ref: str) -> bool:
    return load_winrm_credentials(credential_ref) is not None


def resolve_host_secret_refs(raw: Dict[str, Any]) -> Dict[str, Any]:
    # Resolve env-based secrets if they use the form "env:VAR_NAME".
    # Missing env vars are allowed so UI-provisioned hosts can be visible as
    # not yet operable without storing plaintext credentials.
    for host in raw.get("hosts", []):
        if not host.get("credential_ref"):
            host["credential_ref"] = host.get("address") or host.get("name")
        for key in ("winrm_user", "winrm_pass"):
            val = host.get(key)
            if isinstance(val, str) and val.startswith("env:"):
                env_key = val.split(":", 1)[1]
                env_val = os.getenv(env_key)
                if not env_val:
                    logging.warning(
                        "Missing environment variable '%s' for host '%s' field '%s'",
                        env_key,
                        host.get("name", "<unknown>"),
                        key,
                    )
                host[key] = env_val or ""
        if not host.get("winrm_user") or not host.get("winrm_pass"):
            creds = load_winrm_credentials(credential_ref_for_host(host))
            if creds:
                host["winrm_user"] = creds["user"]
                host["winrm_pass"] = creds["password"]
        if not host.get("winrm_user") or not host.get("winrm_pass"):
            logging.warning("Missing WinRM credentials for host %s", host.get("name", "<unknown>"))
    return raw


def load_config() -> Dict[str, Any]:
    base = read_hosts_config(CONFIG_PATH, missing_ok=False)
    dynamic = read_hosts_config(DYNAMIC_CONFIG_PATH, missing_ok=True)
    return resolve_host_secret_refs(merge_host_configs(base, dynamic))


class HostRegistry:
    def __init__(self, cfg: Dict[str, Any]):
        self.hosts: Dict[str, Dict[str, Any]] = {}
        self.lab_index: Dict[str, Dict[str, Any]] = {}
        for host in cfg.get("hosts", []):
            if "name" not in host or "address" not in host:
                continue
            key = host["name"].lower()
            host["quarantined"] = parse_bool(host.get("quarantined"), False)
            self.hosts[key] = host
            for lab_id in host.get("labs", []):
                lab_key = str(lab_id).strip().lower()
                if not lab_key:
                    continue
                # Only first mapping wins; if multiple hosts share a lab_id, this will pick the first one.
                self.lab_index.setdefault(lab_key, host)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.hosts.get(name.lower()) if name else None

    def get_by_lab(self, lab_id: Optional[Any]) -> Optional[Dict[str, Any]]:
        if lab_id is None:
            return None
        host = self.lab_index.get(str(lab_id).strip().lower())
        if host and host.get("quarantined"):
            return None
        return host

    def all_hosts(self):
        return [h for h in self.hosts.values() if not h.get("quarantined")]

    def set_quarantine(self, name: str, quarantined: bool) -> bool:
        host = self.get(name)
        if not host:
            return False
        host["quarantined"] = bool(quarantined)
        return True

    def count(self) -> int:
        return len(self.hosts)


HOSTS = HostRegistry(load_config())


def build_ops_dsn() -> Optional[str]:
    if MYSQL_DSN:
        return MYSQL_DSN
    if MYSQL_USER and MYSQL_PASSWORD and OPS_MYSQL_DATABASE:
        return URL.create(
            "mysql+pymysql",
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            database=OPS_MYSQL_DATABASE,
        ).render_as_string(hide_password=False)
    return None


OPS_DSN = build_ops_dsn()
DB_ENGINE: Optional[Engine] = create_engine(OPS_DSN, pool_pre_ping=True) if OPS_DSN else None


def build_guacamole_dsn() -> Optional[str]:
    if GUACAMOLE_MYSQL_DSN:
        return GUACAMOLE_MYSQL_DSN
    if MYSQL_USER and MYSQL_PASSWORD and GUACAMOLE_MYSQL_DATABASE:
        return URL.create(
            "mysql+pymysql",
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            database=GUACAMOLE_MYSQL_DATABASE,
        ).render_as_string(hide_password=False)
    if not MYSQL_DSN or not GUACAMOLE_MYSQL_DATABASE:
        return None
    try:
        return str(make_url(MYSQL_DSN).set(database=GUACAMOLE_MYSQL_DATABASE))
    except Exception as exc:
        logging.warning("Unable to derive Guacamole DSN from MYSQL_DSN: %s", exc)
        return None


GUACAMOLE_DSN = build_guacamole_dsn()
GUACAMOLE_DB_ENGINE: Optional[Engine] = (
    create_engine(GUACAMOLE_DSN, pool_pre_ping=True) if GUACAMOLE_DSN else None
)


def to_utc(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Handle trailing Z
        value = str(ts).replace("Z", "+00:00")
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except Exception:
        return None


def wol_and_wait(mac: str, broadcast: Optional[str], port: int, ping_target: str,
                 attempts: int, wait_seconds: float) -> Tuple[bool, int]:
    for attempt in range(1, attempts + 1):
        send_magic_packet(mac, ip_address=broadcast or "255.255.255.255", port=port)
        time.sleep(wait_seconds)
        if host_is_up(ping_target, wait_seconds):
            return True, attempt
    return False, attempts


def host_is_up(target: str, timeout: float) -> bool:
    if not target:
        return False
    cmd = []
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), target]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout)), target]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        logging.warning("ping command not found; skipping reachability check")
    return False


def winrm_endpoint(host: Dict[str, Any], use_ssl: Optional[bool], port: Optional[int]) -> str:
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{host.get('address')}:{port or host.get('winrm_port', 5985)}/wsman"


def run_labstation_command(host: Dict[str, Any], command: str, args: Optional[list],
                           user: Optional[str], password: Optional[str],
                           transport: Optional[str], use_ssl: Optional[bool],
                           port: Optional[int]) -> Dict[str, Any]:
    user = user or host.get("winrm_user")
    password = password or host.get("winrm_pass")
    if not user or not password:
        raise ValueError("WinRM credentials are required")

    endpoint = winrm_endpoint(host, use_ssl, port)
    transport = transport or host.get("winrm_transport", "ntlm")
    exe = host.get("labstation_exe", DEFAULT_LABSTATION_EXE)
    args = args or []

    logging.info("Executing %s %s on %s via %s", exe, command, host.get("name"), endpoint)
    start = time.time()
    session = winrm.Session(
        endpoint,
        auth=(user, password),
        transport=transport,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
    )
    result = session.run_cmd(exe, [command] + args)
    duration_ms = int((time.time() - start) * 1000)

    return {
        "exit_code": result.status_code,
        "stdout": (result.std_out or b"").decode("utf-8", errors="ignore"),
        "stderr": (result.std_err or b"").decode("utf-8", errors="ignore"),
        "duration_ms": duration_ms,
    }


def run_remote_powershell(host: Dict[str, Any], script: str, user: Optional[str], password: Optional[str],
                          transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> str:
    user = user or host.get("winrm_user")
    password = password or host.get("winrm_pass")
    if not user or not password:
        raise ValueError("WinRM credentials are required")

    endpoint = winrm_endpoint(host, use_ssl, port)
    transport = transport or host.get("winrm_transport", "ntlm")
    session = winrm.Session(endpoint, auth=(user, password), transport=transport)
    result = session.run_ps(script)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM PowerShell failed ({result.status_code}): {(result.std_err or b'').decode('utf-8', errors='ignore')}")
    return (result.std_out or b"").decode("utf-8", errors="ignore")


def read_remote_file(host: Dict[str, Any], path: str, user: Optional[str], password: Optional[str],
                     transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> str:
    user = user or host.get("winrm_user")
    password = password or host.get("winrm_pass")
    if not user or not password:
        raise ValueError("WinRM credentials are required")

    endpoint = winrm_endpoint(host, use_ssl, port)
    transport = transport or host.get("winrm_transport", "ntlm")
    ps = f"Get-Content -LiteralPath '{path}' -Raw -Encoding UTF8"

    session = winrm.Session(endpoint, auth=(user, password), transport=transport)
    result = session.run_ps(ps)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM read failed ({result.status_code}): {(result.std_err or b'').decode('utf-8', errors='ignore')}")
    return (result.std_out or b"").decode("utf-8", errors="ignore")


def write_remote_file(host: Dict[str, Any], path: str, contents: str,
                      user: Optional[str], password: Optional[str],
                      transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> None:
    user = user or host.get("winrm_user")
    password = password or host.get("winrm_pass")
    if not user or not password:
        raise ValueError("WinRM credentials are required")

    endpoint = winrm_endpoint(host, use_ssl, port)
    transport = transport or host.get("winrm_transport", "ntlm")
    escaped_path = path.replace("'", "''")
    escaped_contents = contents.replace("'", "''")
    ps = f"Set-Content -LiteralPath '{escaped_path}' -Value '{escaped_contents}' -Encoding UTF8"

    session = winrm.Session(endpoint, auth=(user, password), transport=transport)
    result = session.run_ps(ps)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM write failed ({result.status_code}): {(result.std_err or b'').decode('utf-8', errors='ignore')}")


def remove_remote_file(host: Dict[str, Any], path: str,
                       user: Optional[str], password: Optional[str],
                       transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> None:
    user = user or host.get("winrm_user")
    password = password or host.get("winrm_pass")
    if not user or not password:
        raise ValueError("WinRM credentials are required")

    endpoint = winrm_endpoint(host, use_ssl, port)
    transport = transport or host.get("winrm_transport", "ntlm")
    escaped_path = path.replace("'", "''")
    ps = (
        f"if (Test-Path -LiteralPath '{escaped_path}') {{ Remove-Item -LiteralPath '{escaped_path}' -Force }}"
    )

    session = winrm.Session(endpoint, auth=(user, password), transport=transport)
    result = session.run_ps(ps)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM remove failed ({result.status_code}): {(result.std_err or b'').decode('utf-8', errors='ignore')}")


def get_local_mode_flag_path(host: Dict[str, Any]) -> str:
    return host.get("local_mode_flag_path", r"C:\LabStation\labstation\data\local-mode.flag")


def persist_heartbeat(engine: Engine, host: Dict[str, Any], heartbeat: Dict[str, Any],
                      last_event: Optional[Dict[str, Any]]) -> None:
    ts = to_utc(heartbeat.get("timestamp")) or datetime.now(timezone.utc)
    ready = heartbeat.get("summary", {}).get("ready")
    status = heartbeat.get("status", {})
    operations = heartbeat.get("operations", {})

    last_forced = operations.get("lastForcedLogoff") or {}
    last_power = operations.get("lastPowerAction") or {}
    local_mode = status.get("localModeEnabled")
    local_session = status.get("localSessionActive")

    last_forced_ts = to_utc(last_forced.get("timestamp"))
    last_power_ts = to_utc(last_power.get("timestamp"))

    with engine.begin() as conn:
        host_row = conn.execute(
            text("SELECT id FROM lab_hosts WHERE name=:name"),
            {"name": host.get("name")},
        ).fetchone()
        if host_row:
            host_id = host_row[0]
            conn.execute(
                text("UPDATE lab_hosts SET address=:address, mac=:mac, last_seen=:last_seen WHERE id=:id"),
                {
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                    "id": host_id,
                },
            )
        else:
            res = conn.execute(
                text("INSERT INTO lab_hosts (name, address, mac, last_seen) VALUES (:name, :address, :mac, :last_seen)"),
                {
                    "name": host.get("name"),
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                },
            )
            host_id = res.lastrowid

        conn.execute(
            text(
                """
                INSERT INTO lab_host_heartbeat (
                    host_id, timestamp_utc, ready, local_mode, local_session,
                    last_forced_logoff_ts, last_forced_logoff_user,
                    last_power_action_ts, last_power_action_mode,
                    raw_json
                ) VALUES (
                    :host_id, :ts, :ready, :local_mode, :local_session,
                    :last_forced_ts, :last_forced_user,
                    :last_power_ts, :last_power_mode,
                    :raw_json
                )
                """
            ),
            {
                "host_id": host_id,
                "ts": ts,
                "ready": ready,
                "local_mode": local_mode,
                "local_session": local_session,
                "last_forced_ts": last_forced_ts,
                "last_forced_user": last_forced.get("user"),
                "last_power_ts": last_power_ts,
                "last_power_mode": last_power.get("mode"),
                "raw_json": json.dumps(heartbeat),
            },
        )

        if last_event:
            conn.execute(
                text(
                    """
                    INSERT INTO lab_host_events (host_id, kind, timestamp_utc, payload)
                    VALUES (:host_id, :kind, :ts, :payload)
                    """
                ),
                {
                    "host_id": host_id,
                    "kind": "session-guard",
                    "ts": to_utc(last_event.get("timestamp")) or ts,
                    "payload": json.dumps(last_event),
                },
            )


def parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off")
    return bool(value)


def normalize_args(args: Any, default: Optional[List[str]] = None) -> List[str]:
    if args is None:
        return list(default or [])
    if isinstance(args, list):
        return [str(item) for item in args]
    return [str(args)]


def parse_recipients(value: Any, default: Optional[List[str]] = None) -> List[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    recipients: List[str] = []
    for item in items:
        for part in item.split(","):
            normalized = part.strip()
            if normalized:
                recipients.append(normalized)
    return recipients


NOTIFICATION_SERVICE_RECIPIENTS = parse_recipients(os.getenv("NOTIFICATION_SERVICE_RECIPIENTS"))

OPS_ALERT_FAILURE_THRESHOLD = max(1, int(os.getenv("OPS_ALERT_FAILURE_THRESHOLD", "3")))
OPS_ALERT_WINDOW_SECONDS = max(60, int(os.getenv("OPS_ALERT_WINDOW_SECONDS", "300")))
OPS_ALERT_COOLDOWN_SECONDS = max(60, int(os.getenv("OPS_ALERT_COOLDOWN_SECONDS", "900")))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def record_reservation_operation(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    action: str,
    status: str,
    success: bool,
    response_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
):
    if not DB_ENGINE:
        return
    created_at = _now_utc()
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO reservation_operations (
                        reservation_id, lab_id, host, action, status, success,
                        response_code, duration_ms, payload, message, created_at
                    ) VALUES (
                        :reservation_id, :lab_id, :host, :action, :status, :success,
                        :response_code, :duration_ms, :payload, :message, :created_at
                    )
                    """
                ),
                {
                    "reservation_id": reservation_id,
                    "lab_id": lab_id,
                    "host": host_name,
                    "action": action,
                    "status": status,
                    "success": success,
                    "response_code": response_code,
                    "duration_ms": duration_ms,
                    "payload": json.dumps(payload) if payload is not None else None,
                    "message": message,
                    "created_at": created_at,
                },
            )
        if not success and action not in ("notification", "alert"):
            try:
                _check_failure_alert(host_name, reservation_id, lab_id, action, message, payload)
            except Exception as exc:
                logging.warning("Failure alert check failed for %s: %s", host_name, exc)
    except Exception as exc:
        logging.error("Failed to persist reservation operation %s/%s: %s", reservation_id, action, exc)


def _should_send_failure_alert(host_name: str) -> bool:
    if not DB_ENGINE or not host_name:
        return False
    if not NOTIFICATION_SERVICE_ENABLED or not NOTIFICATION_SERVICE_URL:
        return False

    now = _now_utc()
    window_start = now - timedelta(seconds=OPS_ALERT_WINDOW_SECONDS)
    cooldown_start = now - timedelta(seconds=OPS_ALERT_COOLDOWN_SECONDS)

    with DB_ENGINE.begin() as conn:
        failure_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM reservation_operations "
                "WHERE host = :host AND success = 0 "
                "AND action NOT IN ('notification', 'alert') "
                "AND created_at >= :window_start"
            ),
            {"host": host_name, "window_start": window_start},
        ).scalar() or 0

        recent_alert = conn.execute(
            text(
                "SELECT 1 FROM reservation_operations "
                "WHERE host = :host AND action = 'alert' "
                "AND created_at >= :cooldown_start LIMIT 1"
            ),
            {"host": host_name, "cooldown_start": cooldown_start},
        ).scalar()

    return failure_count >= OPS_ALERT_FAILURE_THRESHOLD and recent_alert is None


def _send_failure_alert(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    subject = f"Lab Gateway alert: repeated failures for {host_name}"
    body = [
        f"Reservation: {reservation_id}",
        f"Lab ID: {lab_id or 'unknown'}",
        f"Host: {host_name}",
        f"Condition: {failure_reason}",
    ]
    if details:
        body.append(f"Details: {json.dumps(details, default=str)}")

    recipients = list(NOTIFICATION_SERVICE_RECIPIENTS)
    payload = {
        "recipients": recipients,
        "subject": subject,
        "textBody": "\n".join(body),
        "htmlBody": "<p>" + "</p><p>".join(body) + "</p>",
        "icsContent": None,
        "icsFileName": None,
    }
    headers = {"Content-Type": "application/json"}
    if NOTIFICATION_SERVICE_ACCESS_TOKEN:
        headers[NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER] = NOTIFICATION_SERVICE_ACCESS_TOKEN

    attempt = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
        attempt += 1
        start = time.time()
        try:
            response = requests.post(NOTIFICATION_SERVICE_URL, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            if success:
                break
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)
        except Exception as exc:
            last_exception = exc
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)

    if response is not None and response.ok:
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "alert",
            "completed",
            True,
            response_code=status_code,
            payload={
                "failureReason": failure_reason,
                "attempts": attempt,
                "response": resp_text,
            },
            message=f"Alert sent after {attempt} attempt(s)",
        )
    else:
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "alert",
            "failed",
            False,
            response_code=status_code,
            payload={
                "failureReason": failure_reason,
                "attempts": attempt,
                "response": resp_text,
                "exception": str(last_exception) if last_exception else None,
            },
            message=(
                f"Alert failed after {attempt} attempt(s): {resp_text or last_exception}"
            ),
        )


def _check_failure_alert(
    host_name: str,
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    message: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> None:
    if not _should_send_failure_alert(host_name):
        return

    failure_reason = (
        f"At least {OPS_ALERT_FAILURE_THRESHOLD} failed operations in the last {OPS_ALERT_WINDOW_SECONDS} seconds"
    )
    details = {
        "triggerAction": action,
        "triggerMessage": message,
        "payload": payload,
    }
    _send_failure_alert(reservation_id, lab_id, host_name, failure_reason, details)


def notify_critical_failure(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    action: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    if not NOTIFICATION_SERVICE_ENABLED or not NOTIFICATION_SERVICE_URL:
        return

    subject = f"Lab Gateway alert: {action} failed for {host_name}"
    body = [
        f"Reservation: {reservation_id}",
        f"Lab ID: {lab_id or 'unknown'}",
        f"Host: {host_name}",
        f"Action: {action}",
        f"Reason: {failure_reason}",
    ]
    if details:
        body.append(f"Details: {json.dumps(details, default=str)}")

    recipients = list(NOTIFICATION_SERVICE_RECIPIENTS)
    payload = {
        "recipients": recipients,
        "subject": subject,
        "textBody": "\n".join(body),
        "htmlBody": "<p>" + "</p><p>".join(body) + "</p>",
        "icsContent": None,
        "icsFileName": None,
    }
    headers = {"Content-Type": "application/json"}
    if NOTIFICATION_SERVICE_ACCESS_TOKEN:
        headers[NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER] = NOTIFICATION_SERVICE_ACCESS_TOKEN

    attempt = 0
    duration_ms = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
        attempt += 1
        start = time.time()
        try:
            response = requests.post(NOTIFICATION_SERVICE_URL, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            duration_ms = int((time.time() - start) * 1000)
            if success:
                break
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)
        except Exception as exc:
            last_exception = exc
            duration_ms = int((time.time() - start) * 1000)
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)

    if response is not None and response.ok:
        op_payload = {
            "failureAction": action,
            "notificationUrl": NOTIFICATION_SERVICE_URL,
            "attempts": attempt,
            "response": resp_text,
        }
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "notification",
            "completed",
            True,
            response_code=status_code,
            duration_ms=duration_ms,
            payload=op_payload,
            message=f"Notification sent after {attempt} attempt(s)",
        )
    else:
        error_details = {
            "failureAction": action,
            "notificationUrl": NOTIFICATION_SERVICE_URL,
            "attempts": attempt,
            "response": resp_text,
        }
        if last_exception is not None:
            error_details["exception"] = str(last_exception)
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "notification",
            "failed",
            False,
            response_code=status_code,
            duration_ms=duration_ms,
            payload=error_details,
            message=(
                f"Notification failed after {attempt} attempt(s): {resp_text or last_exception}"
            ),
        )


def perform_wake_step(
    host: Dict[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    options: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    mac = options.get("mac") or host.get("mac")
    if not mac:
        message = "MAC address not configured"
        record_reservation_operation(reservation_id, lab_id, host.get("name", ""), "wake", "failed", False, message=message)
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {}
        }

    ping_target = options.get("ping_target") or host.get("ping_target") or host.get("address")
    if not ping_target:
        message = "Ping target not configured"
        record_reservation_operation(reservation_id, lab_id, host.get("name", ""), "wake", "failed", False, message=message)
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {}
        }

    attempts = int(options.get("attempts", host.get("wake_attempts", 3)))
    wait_seconds = float(options.get("ping_timeout", 10))
    broadcast = options.get("broadcast") or host.get("broadcast")
    port = int(options.get("port", host.get("wol_port", 9)))

    start = time.time()
    success = False
    used_attempts = 0
    message = ""
    try:
        success, used_attempts = wol_and_wait(mac, broadcast, port, ping_target, attempts, wait_seconds)
        message = "Host reachable" if success else "Host did not respond to ping"
    except Exception as exc:
        message = str(exc)
    duration_ms = int((time.time() - start) * 1000)
    status = "completed" if success else "failed"
    details = {
        "mac": mac,
        "pingTarget": ping_target,
        "attemptsRequested": attempts,
        "attemptsUsed": used_attempts,
        "waitSeconds": wait_seconds,
        "port": port,
        "broadcast": broadcast,
    }
    record_reservation_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        "wake",
        status,
        success,
        response_code=200 if success else 504,
        duration_ms=duration_ms,
        payload=details,
        message=message,
    )
    if not success:
        notify_critical_failure(reservation_id, lab_id, host.get("name", ""), "wake", message, details)
    return success, {
        "action": "wake",
        "success": success,
        "status": status,
        "message": message,
        "durationMs": duration_ms,
        "details": details,
    }


def perform_command_step(
    host: Dict[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    command: str,
    args: List[str],
) -> Tuple[bool, Dict[str, Any]]:
    start = time.time()
    success = False
    result: Dict[str, Any] = {}
    message = ""
    try:
        result = run_labstation_command(host, command, args, None, None, None, None, None)
        success = result.get("exit_code", 1) == 0
        message = "Exit code {}".format(result.get("exit_code"))
    except Exception as exc:
        message = str(exc)
        result = {"error": message}
    duration_ms = result.get("duration_ms", int((time.time() - start) * 1000))
    status = "completed" if success else "failed"
    summarized = {
        "exitCode": result.get("exit_code"),
        "stdout": (result.get("stdout") or "").strip(),
        "stderr": (result.get("stderr") or "").strip(),
        "args": args,
        "durationMs": duration_ms,
    }
    record_reservation_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        action,
        status,
        success,
        response_code=result.get("exit_code"),
        duration_ms=duration_ms,
        payload=summarized,
        message=message,
    )
    if not success:
        notify_critical_failure(reservation_id, lab_id, host.get("name", ""), action, message, summarized)
    return success, {
        "action": action,
        "success": success,
        "status": status,
        "message": message,
        "details": summarized,
    }


def poll_heartbeat(host: Dict[str, Any], include_events: bool = False) -> Dict[str, Any]:
    hb_path = host.get("heartbeat_path", r"C:\LabStation\labstation\data\telemetry\heartbeat.json")
    events_path = host.get("events_path", r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl")
    content = read_remote_file(host, hb_path, None, None, None, None, None)
    heartbeat = json.loads(content)
    last_event = None
    if include_events:
        try:
            tail = read_remote_file(host, events_path, None, None, None, None, None)
            if tail.strip():
                last_event = json.loads(tail.strip().splitlines()[-1])
        except Exception as exc:
            logging.warning("Could not read events for %s: %s", host.get("name"), exc)
    if DB_ENGINE:
        try:
            persist_heartbeat(DB_ENGINE, host, heartbeat, last_event)
        except Exception as exc:
            logging.error("DB persistence failed for %s: %s", host.get("name"), exc)
    # Auto-sync AAS TechnicalData on heartbeat (best-effort, never blocks the poll)
    for lab_id in host.get("labs", []):
        try:
            sync_result = aas_generator.sync_lab_to_basyx(str(lab_id), host, heartbeat)
            if sync_result.get("disabled"):
                break  # AAS not configured on this gateway — skip remaining labs silently
            if sync_result.get("error"):
                logging.warning("AAS auto-sync failed for lab %s: %s", lab_id, sync_result["error"])
            else:
                logging.debug("AAS auto-synced for lab %s", lab_id)
        except Exception as exc:
            logging.warning("AAS auto-sync exception for lab %s: %s", lab_id, exc)
    return {"heartbeat": heartbeat, "last_event": last_event}


def database_is_usable(engine: Optional[Engine], statement: str) -> bool:
    if not engine:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text(statement)).first()
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Health database check failed: %s", exc)
        return False


@APP.route("/health", methods=["GET"])
def health():
    db_ok = database_is_usable(DB_ENGINE, "SELECT 1")
    guacamole_schema_ok = database_is_usable(
        GUACAMOLE_DB_ENGINE,
        """
        SELECT 1
        FROM guacamole_entity e
        LEFT JOIN guacamole_user u ON u.entity_id = e.entity_id
        LEFT JOIN guacamole_connection_permission cp ON cp.entity_id = e.entity_id
        LEFT JOIN guacamole_connection c ON c.connection_id = cp.connection_id
        LIMIT 1
        """,
    )
    healthy = db_ok and guacamole_schema_ok
    return jsonify({
        "status": "ok" if healthy else "degraded",
        "hosts_loaded": len(HOSTS.all_hosts()),
        "db": db_ok,
        "guacamole_schema": guacamole_schema_ok,
    }), 200 if healthy else 503


@APP.route("/api/wol", methods=["POST"])
def api_wol():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    host = HOSTS.get(host_name) if host_name else None
    mac = payload.get("mac") or (host or {}).get("mac")
    if not mac:
        return jsonify({"error": "mac is required"}), 400

    ping_target = str(payload.get("ping_target") or (host or {}).get("ping_target") or (host or {}).get("address") or "").strip()
    if not ping_target:
        return jsonify({"error": "ping_target or host address is required"}), 400
    attempts = int(payload.get("attempts", 3))
    wait_seconds = float(payload.get("ping_timeout", 10))
    broadcast = payload.get("broadcast")
    port = int(payload.get("port", 9))

    start = time.time()
    try:
        up, used_attempts = wol_and_wait(mac, broadcast, port, ping_target, attempts, wait_seconds)
    except Exception as exc:
        logging.exception("WOL failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "success": up,
        "attempts_used": used_attempts,
        "duration_ms": int((time.time() - start) * 1000),
        "ping_target": ping_target,
    })


@APP.route("/api/winrm", methods=["POST"])
def api_winrm():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    command = payload.get("command")
    args = payload.get("args") or []
    if not host_name or not command:
        return jsonify({"error": "host and command are required"}), 400
    if command not in ALLOWED_WINRM_COMMANDS:
        return jsonify({"error": f"command '{command}' not allowed"}), 400
    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        result = run_labstation_command(
            host=host,
            command=command,
            args=args,
            user=payload.get("user"),
            password=payload.get("password"),
            transport=payload.get("transport"),
            use_ssl=payload.get("use_ssl"),
            port=payload.get("port"),
        )
        return jsonify(result)
    except Exception as exc:
        logging.exception("WinRM exec failed")
        return jsonify({"error": str(exc)}), 500


@APP.route("/api/heartbeat/poll", methods=["POST"])
def api_poll_heartbeat():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    include_events = bool(payload.get("include_events", True))
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    start = time.time()
    try:
        data = poll_heartbeat(host, include_events=include_events)
        data["duration_ms"] = int((time.time() - start) * 1000)
        data["host"] = host_name
        return jsonify(data)
    except Exception as exc:
        logging.exception("Heartbeat poll failed")
        return jsonify({"error": str(exc)}), 500


def _format_sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def generate_heartbeat_stream(host: Dict[str, Any], include_events: bool):
    while True:
        try:
            data = poll_heartbeat(host, include_events=include_events)
            data["host"] = host.get("name")
            yield _format_sse_event("heartbeat", json.dumps(data))
        except Exception as exc:
            yield _format_sse_event("error", json.dumps({"error": str(exc), "host": host.get("name")}))
        time.sleep(HEARTBEAT_SSE_INTERVAL_SECONDS)


@APP.route("/api/heartbeat/stream", methods=["GET"])
def api_stream_heartbeat():
    host_name = request.args.get("host")
    include_events = request.args.get("include_events", "true").strip().lower() not in ("0", "false", "no", "off")
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404
    response = Response(
        stream_with_context(generate_heartbeat_stream(host, include_events)),
        content_type="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


def _get_mandatory_field(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def handle_reservation_start(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = HOSTS.get(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    wake_enabled = parse_bool(payload.get("wake", True), True)
    prepare_enabled = parse_bool(payload.get("prepare", True), True)
    guard_grace = int(payload.get("guardGrace", 90))
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if wake_enabled:
        ok, step = perform_wake_step(host, reservation_id, lab_id, payload.get("wakeOptions", {}))
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and prepare_enabled:
        prepare_args = normalize_args(payload.get("prepareArgs"), [f"--guard-grace={guard_grace}"])
        ok, step = perform_command_step(host, reservation_id, lab_id, "prepare", "prepare-session", prepare_args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


def handle_reservation_end(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = HOSTS.get(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    release_enabled = parse_bool(payload.get("release", True), True)
    power_cfg = payload.get("powerAction")
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if release_enabled:
        release_args = normalize_args(payload.get("releaseArgs"), ["--reboot"])
        ok, step = perform_command_step(host, reservation_id, lab_id, "release", "release-session", release_args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and power_cfg:
        mode = power_cfg.get("mode", "shutdown")
        extra_args = normalize_args(power_cfg.get("args"), [])
        args = [mode] + extra_args
        ok, step = perform_command_step(host, reservation_id, lab_id, f"power:{mode}", "power", args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


@APP.route("/api/reservations/start", methods=["POST"])
def api_reservation_start():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_reservation_start(payload)
    return jsonify(response), status


@APP.route("/api/reservations/end", methods=["POST"])
def api_reservation_end():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_reservation_end(payload)
    return jsonify(response), status


def _to_iso(dt: Any) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt)
        except ValueError:
            return dt
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _sanitize_limit(value: Optional[str]) -> int:
    if value is None:
        return TIMELINE_DEFAULT_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return TIMELINE_DEFAULT_LIMIT
    return max(1, min(parsed, TIMELINE_MAX_LIMIT))


def _sanitize_offset(value: Optional[str]) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _rows_to_operations(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    op_entries: List[Dict[str, Any]] = []
    for op in rows:
        payload = op.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        op_entries.append(
            {
                "action": op.get("action"),
                "status": op.get("status"),
                "success": bool(op.get("success")),
                "message": op.get("message"),
                "payload": payload,
                "responseCode": op.get("response_code"),
                "durationMs": op.get("duration_ms"),
                "createdAt": _to_iso(op.get("created_at")),
            }
        )
    return op_entries


def build_reservation_timeline(reservation_id: str, limit: int, offset: int) -> Dict[str, Any]:
    if not DB_ENGINE:
        raise RuntimeError("Database not configured")

    with DB_ENGINE.begin() as conn:
        reservation = conn.execute(
            text(
                """
                SELECT transaction_hash, lab_id, status, start_time, end_time,
                       wallet_address, created_at, updated_at
                FROM lab_reservations
                WHERE transaction_hash = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).mappings().first()

        if not reservation:
            raise LookupError("Reservation not found")

        lab_id = reservation.get("lab_id")
        host = HOSTS.get_by_lab(lab_id)
        host_name = (host or {}).get("name")

        # Get total count for pagination metadata
        total_ops = conn.execute(
            text(
                """
                SELECT COUNT(*) as total
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).scalar()
        
        operations = conn.execute(
            text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at ASC, id ASC
                LIMIT :limit_value OFFSET :offset_value
                """
            ),
            {
                "reservation_id": reservation_id,
                "limit_value": limit,
                "offset_value": offset,
            },
        ).mappings().all()
        op_entries = _rows_to_operations([dict(row) for row in operations])

        phase_rows = conn.execute(
            text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at DESC, id DESC
                LIMIT :phase_limit
                """
            ),
            {"reservation_id": reservation_id, "phase_limit": TIMELINE_PHASE_LOOKBACK},
        ).mappings().all()
        phase_entries = _rows_to_operations([dict(row) for row in reversed(phase_rows)])

        latest_heartbeat = None
        if host_name:
            latest_heartbeat = _fetch_latest_heartbeat(conn, host_name)

        phases = _summarize_phases(phase_entries)

        reservation_payload = {
            "reservationId": reservation.get("transaction_hash"),
            "labId": lab_id,
            "status": reservation.get("status"),
            "start": _to_iso(reservation.get("start_time")),
            "end": _to_iso(reservation.get("end_time")),
            "walletAddress": reservation.get("wallet_address"),
            "createdAt": _to_iso(reservation.get("created_at")),
            "updatedAt": _to_iso(reservation.get("updated_at")),
        }

        returned_count = len(op_entries)
        total_ops = total_ops or 0
        next_offset = offset + returned_count
        has_more = total_ops > next_offset
        page = (offset // limit) + 1 if limit else 1

        return {
            "reservation": reservation_payload,
            "host": {
                "name": host_name,
                "labId": lab_id,
                "config": host,
            },
            "operations": op_entries,
            "phases": phases,
            "heartbeat": latest_heartbeat,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "page": page,
                "pageSize": limit,
                "returned": returned_count,
                "total": total_ops,
                "hasMore": has_more,
                "nextOffset": next_offset,
            },
        }


def _fetch_latest_heartbeat(conn: Connection, host_name: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT h.timestamp_utc, h.ready, h.local_mode, h.local_session,
                   h.last_power_action_ts, h.last_power_action_mode,
                   h.last_forced_logoff_ts, h.last_forced_logoff_user,
                   h.raw_json
            FROM lab_host_heartbeat h
            JOIN lab_hosts ho ON ho.id = h.host_id
            WHERE ho.name = :host
            ORDER BY h.timestamp_utc DESC
            LIMIT 1
            """
        ),
        {"host": host_name},
    ).mappings().first()

    if not row:
        return None

    raw = row.get("raw_json")
    parsed_raw = None
    if isinstance(raw, str):
        try:
            parsed_raw = json.loads(raw)
        except json.JSONDecodeError:
            parsed_raw = None

    return {
        "timestamp": _to_iso(row.get("timestamp_utc")),
        "ready": bool(row.get("ready")),
        "localMode": bool(row.get("local_mode")),
        "localSession": bool(row.get("local_session")),
        "lastPower": {
            "timestamp": _to_iso(row.get("last_power_action_ts")),
            "mode": row.get("last_power_action_mode"),
        },
        "lastForcedLogoff": {
            "timestamp": _to_iso(row.get("last_forced_logoff_ts")),
            "user": row.get("last_forced_logoff_user"),
        },
        "raw": parsed_raw,
    }


def _summarize_phases(operations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def picker(prefixes: List[str]) -> Optional[Mapping[str, Any]]:
        for entry in reversed(operations):
            action = entry.get("action") or ""
            if any(action.startswith(prefix) for prefix in prefixes):
                return entry
        return None

    return {
        "wake": picker(["wake", "scheduler:start"]),
        "prepare": picker(["prepare"]),
        "release": picker(["release"]),
        "power": picker(["power:"]),
        "schedulerEnd": picker(["scheduler:end"]),
    }


@APP.route("/api/reservations/timeline", methods=["GET"])
def api_reservation_timeline():
    if not DB_ENGINE:
        return jsonify({"error": "Database not configured"}), 500
    reservation_id = request.args.get("reservationId") or request.args.get("reservation_id")
    if not reservation_id:
        return jsonify({"error": "reservationId is required"}), 400
    limit = _sanitize_limit(request.args.get("limit"))
    offset = _sanitize_offset(request.args.get("offset"))
    try:
        data = build_reservation_timeline(reservation_id, limit, offset)
    except LookupError:
        return jsonify({"error": "Reservation not found"}), 404
    except RuntimeError as exc:
        logging.error("Timeline error: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(data)


def normalize_match_key(value: Optional[Any]) -> str:
    return str(value or "").strip().lower()


def tcp_port_open(host: str, port: int, timeout: Optional[float] = None) -> bool:
    try:
        with socket.create_connection((host, port), timeout or DISCOVERY_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def response_looks_like_labstation(response: requests.Response) -> Tuple[bool, Optional[str]]:
    service = None
    try:
        body = response.json()
        if isinstance(body, dict):
            service = body.get("service") or body.get("name") or body.get("app")
            text_blob = json.dumps(body).lower()
        else:
            text_blob = str(body).lower()
    except ValueError:
        text_blob = response.text.lower()

    detected = "labstation" in text_blob or str(service or "").lower() == "labstation"
    return detected, service


def normalize_env_name_from_host(host: Any, prefix: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(host or "LAB_HOST").upper()).strip("_")
    return f"{prefix}_{normalized or 'LAB_HOST'}"


def normalize_mac(value: Any) -> str:
    candidate = str(value or "").strip()
    if not MAC_RE.fullmatch(candidate):
        return ""
    return candidate.replace("-", ":").upper()


def parse_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled", "up"}


def extract_nic_candidates_from_heartbeat(heartbeat: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_status = heartbeat.get("status")
    status = raw_status if isinstance(raw_status, dict) else heartbeat
    raw_wake = status.get("wake")
    wake = raw_wake if isinstance(raw_wake, dict) else {}
    raw_adapters = wake.get("nicPower")
    adapters = raw_adapters if isinstance(raw_adapters, list) else []
    candidates = []
    for adapter in adapters:
        if not isinstance(adapter, dict):
            continue
        mac = normalize_mac(adapter.get("macAddress") or adapter.get("mac") or adapter.get("physicalAddress"))
        if not mac:
            continue
        candidates.append({
            "mac": mac,
            "name": adapter.get("name") or adapter.get("interfaceAlias") or "",
            "status": adapter.get("status") or "",
            "wolReady": parse_boolish(adapter.get("wolReady")),
            "wakeArmed": parse_boolish(adapter.get("wakeArmed")),
        })
    return candidates


def choose_wol_mac(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    def score(candidate: Dict[str, Any]) -> Tuple[int, int, int]:
        status = str(candidate.get("status") or "").strip().lower()
        return (
            1 if candidate.get("wolReady") else 0,
            1 if status == "up" else 0,
            1 if candidate.get("wakeArmed") else 0,
        )

    best = sorted(candidates, key=score, reverse=True)[0]
    return {"mac": best["mac"], "source": "status.wake.nicPower", "adapter": best}


def suggest_mac_from_heartbeat(heartbeat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return choose_wol_mac(extract_nic_candidates_from_heartbeat(heartbeat))


def probe_labstation_http(host: str) -> Dict[str, Any]:
    if not host:
        return {"checked": False, "detected": False, "status": "missing-hostname"}

    for port in DISCOVERY_LABSTATION_PORTS:
        for path in DISCOVERY_LABSTATION_PATHS:
            url = f"http://{host}:{port}{path}"
            try:
                response = requests.get(url, timeout=DISCOVERY_TIMEOUT_SECONDS)
            except requests.RequestException:
                continue
            detected, service = response_looks_like_labstation(response)
            if detected:
                result = {
                    "checked": True,
                    "detected": True,
                    "url": url,
                    "statusCode": response.status_code,
                    "service": service,
                }
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        mac_hint = suggest_mac_from_heartbeat(body)
                        if mac_hint:
                            result["suggestedMac"] = mac_hint
                except ValueError:
                    pass
                return result

    return {"checked": True, "detected": False, "status": "no-response"}


def query_labstation_task_heartbeat_path(host: Dict[str, Any]) -> Optional[str]:
    script = r"""
$task = Get-ScheduledTask -TaskPath '\LabStation\' -TaskName 'BackgroundService' -ErrorAction Stop
$action = @($task.Actions)[0]
$execute = [string]$action.Execute
$arguments = [string]$action.Arguments
$heartbeatPath = ''
if ($arguments -match '"([^"]*\\LabStation\.ahk)"') {
    $root = Split-Path -Parent $Matches[1]
    $heartbeatPath = Join-Path $root 'data\telemetry\heartbeat.json'
} elseif ($execute -match '(?i)LabStation\.exe$') {
    $root = Split-Path -Parent $execute.Trim('"')
    $heartbeatPath = Join-Path $root 'data\telemetry\heartbeat.json'
}
[pscustomobject]@{
    execute = $execute
    arguments = $arguments
    heartbeatPath = $heartbeatPath
} | ConvertTo-Json -Compress
"""
    try:
        raw = run_remote_powershell(host, script, None, None, None, None, None)
        parsed = json.loads(raw)
    except Exception as exc:  # pylint: disable=broad-except
        logging.debug("Unable to derive Lab Station heartbeat path from scheduled task: %s", exc)
        return None
    path = str(parsed.get("heartbeatPath") or "").strip() if isinstance(parsed, dict) else ""
    return path or None


def build_heartbeat_path_candidates(host: Dict[str, Any]) -> List[str]:
    candidates = []
    task_path = query_labstation_task_heartbeat_path(host)
    if task_path:
        candidates.append(task_path)
    for path in DISCOVERY_HEARTBEAT_PATHS:
        if path and path not in candidates:
            candidates.append(path)
    return candidates


def discover_heartbeat_hint(hostname: str) -> Dict[str, Any]:
    if not hostname:
        return {"checked": False, "detected": False, "status": "missing-hostname"}
    user_env = normalize_env_name_from_host(hostname, 'WINRM_USER')
    pass_env = normalize_env_name_from_host(hostname, 'WINRM_PASS')
    stored_creds = load_winrm_credentials(hostname) or {}
    temp_host = {
        "name": hostname,
        "address": hostname,
        "credential_ref": hostname,
        "winrm_user": stored_creds.get("user") or os.getenv(user_env) or "",
        "winrm_pass": stored_creds.get("password") or os.getenv(pass_env) or "",
        "winrm_transport": "ntlm",
    }
    if not temp_host.get("winrm_user") or not temp_host.get("winrm_pass"):
        return {"checked": False, "detected": False, "status": "missing-winrm-env"}
    errors = []
    heartbeat = None
    detected_path = None
    for path in build_heartbeat_path_candidates(temp_host):
        try:
            raw = read_remote_file(
                temp_host,
                path,
                None,
                None,
                None,
                None,
                None,
            )
            heartbeat = json.loads(raw)
            detected_path = path
            break
        except Exception as exc:  # pylint: disable=broad-except
            errors.append({"path": path, "error": str(exc)})

    if heartbeat is None:
        return {"checked": True, "detected": False, "status": "read-failed", "errors": errors}

    mac_hint = suggest_mac_from_heartbeat(heartbeat)
    result = {"checked": True, "detected": True, "path": detected_path}
    if mac_hint:
        result["suggestedMac"] = mac_hint
    return result


def guacamole_name_candidates(connection: Dict[str, Any]) -> List[str]:
    host_key = normalize_match_key(connection.get("hostname"))
    candidates = []
    connections, _ = load_guacamole_connections()
    for item in connections:
        if normalize_match_key(item.get("hostname")) != host_key:
            continue
        text = str(item.get("name") or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    for item in connections:
        if normalize_match_key(item.get("hostname")) != host_key:
            continue
        text = str(item.get("hostname") or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    fallback = str(connection.get("hostname") or connection.get("name") or "").strip()
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates


def resolve_guacamole_connection(connection_id: Any) -> Optional[Dict[str, Any]]:
    try:
        wanted = int(connection_id)
    except (TypeError, ValueError):
        return None
    connections, _ = load_guacamole_connections()
    for connection in connections:
        if connection.get("id") == wanted:
            return connection
    return None


def discover_labstation_candidate(connection: Dict[str, Any]) -> Dict[str, Any]:
    host = normalize_match_key(connection.get("hostname"))
    if not host:
        return {
            "connection": connection,
            "status": "missing-hostname",
            "checks": {
                "dns": False,
                "winrm": {},
                "labStationHttp": {"checked": False, "detected": False, "status": "missing-hostname"},
            },
        }

    try:
        socket.getaddrinfo(host, None)
        dns_ok = True
    except OSError:
        dns_ok = False

    winrm_checks = {
        str(port): tcp_port_open(host, port, DISCOVERY_TIMEOUT_SECONDS)
        for port in DISCOVERY_WINRM_PORTS
    }
    labstation_http = probe_labstation_http(host)
    heartbeat_hint = discover_heartbeat_hint(host) if any(winrm_checks.values()) else {
        "checked": False,
        "detected": False,
        "status": "winrm-unreachable",
    }
    mac_hint = labstation_http.get("suggestedMac") or heartbeat_hint.get("suggestedMac")

    if labstation_http.get("detected") is True:
        status = "labstation-detected"
    elif any(winrm_checks.values()):
        status = "winrm-reachable"
    elif dns_ok:
        status = "host-resolves"
    else:
        status = "no-response"

    ops_host_draft = {
        "name": connection.get("hostname"),
        "address": connection.get("hostname"),
        "winrm_transport": "ntlm",
        "heartbeat_path": heartbeat_hint.get("path") or DISCOVERY_HEARTBEAT_PATHS[0],
        "events_path": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        "labs": [],
        "nameCandidates": guacamole_name_candidates(connection),
    }
    if mac_hint:
        ops_host_draft["mac"] = mac_hint["mac"]

    return {
        "connection": connection,
        "status": status,
        "checks": {
            "dns": dns_ok,
            "winrm": winrm_checks,
            "labStationHttp": labstation_http,
            "heartbeat": heartbeat_hint,
        },
        "opsHostDraft": ops_host_draft,
    }


def require_env_ref_name(value: Any, field: str) -> Tuple[Optional[str], Optional[str]]:
    candidate = str(value or "").strip()
    if candidate.startswith("env:"):
        candidate = candidate.split(":", 1)[1].strip()
    if not ENV_VAR_NAME_RE.fullmatch(candidate):
        return None, f"{field} must be an environment variable name like WINRM_USER_LAB_WS_01"
    return candidate, None


def sanitize_host_name(value: Any, fallback: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
    name = str(value or fallback or "").strip()
    if not HOST_NAME_RE.fullmatch(name):
        return None, "name must contain only letters, numbers, dots, underscores, and hyphens"
    return name, None


def normalize_labs(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        parts = []
    return [str(part).strip() for part in parts if str(part).strip()]


def validate_labs_against_candidates(labs: List[str], candidates: Any) -> Optional[str]:
    if candidates is None:
        return None
    valid = set(normalize_labs(candidates))
    if not valid:
        return "validLabIds must contain at least one lab candidate when provided"
    invalid = [lab for lab in labs if lab not in valid]
    if invalid:
        return f"labs contain values that are not valid candidates: {', '.join(invalid)}"
    return None


def load_dynamic_config() -> Dict[str, Any]:
    return read_hosts_config(DYNAMIC_CONFIG_PATH, missing_ok=True)


def write_dynamic_config(config: Dict[str, Any]) -> None:
    directory = os.path.dirname(DYNAMIC_CONFIG_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{DYNAMIC_CONFIG_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, DYNAMIC_CONFIG_PATH)


def upsert_dynamic_host(host_config: Dict[str, Any]) -> None:
    config = load_dynamic_config()
    hosts = [host for host in config.get("hosts", []) if isinstance(host, dict)]
    key = str(host_config.get("name") or "").strip().lower()
    replaced = False
    for index, host in enumerate(hosts):
        if str(host.get("name") or "").strip().lower() == key:
            hosts[index] = host_config
            replaced = True
            break
    if not replaced:
        hosts.append(host_config)
    config["hosts"] = hosts
    write_dynamic_config(config)


def build_provisioned_host(payload: Dict[str, Any], connection: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    fallback_name = connection.get("hostname") or connection.get("name")
    name, error = sanitize_host_name(payload.get("name"), fallback_name)
    if error:
        return None, error
    address = str(payload.get("address") or connection.get("hostname") or "").strip()
    if not address:
        return None, "address is required"

    labs = normalize_labs(payload.get("labs"))
    labs_error = validate_labs_against_candidates(labs, payload.get("validLabIds"))
    if labs_error:
        return None, labs_error
    credential_ref = str(payload.get("credentialRef") or address).strip()

    host_config = {
        "name": name,
        "address": address,
        "credential_ref": credential_ref,
        "winrm_transport": str(payload.get("winrmTransport") or "ntlm").strip() or "ntlm",
        "heartbeat_path": str(
            payload.get("heartbeatPath")
            or r"C:\LabStation\labstation\data\telemetry\heartbeat.json"
        ),
        "events_path": str(
            payload.get("eventsPath")
            or r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl"
        ),
        "labs": labs,
    }
    mac = str(payload.get("mac") or "").strip()
    if mac:
        host_config["mac"] = mac
    return host_config, None


def safe_host_inventory_entry(host: Dict[str, Any]) -> Dict[str, Any]:
    credential_ref = credential_ref_for_host(host)
    return {
        "name": host.get("name"),
        "address": host.get("address"),
        "credentialRef": credential_ref,
        "mac": host.get("mac"),
        "mode": host.get("mode"),
        "labs": [str(lab) for lab in host.get("labs", [])],
        "quarantined": bool(host.get("quarantined", False)),
        "winrmConfigured": bool(host.get("winrm_user") and host.get("winrm_pass")) or winrm_credentials_configured(credential_ref),
    }


def load_guacamole_connections() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not GUACAMOLE_DB_ENGINE:
        return [], "Guacamole database not configured"

    try:
        with GUACAMOLE_DB_ENGINE.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        c.connection_id,
                        c.connection_name,
                        c.protocol,
                        MAX(CASE WHEN p.parameter_name = 'hostname' THEN p.parameter_value END) AS hostname,
                        MAX(CASE WHEN p.parameter_name = 'port' THEN p.parameter_value END) AS port
                    FROM guacamole_connection c
                    LEFT JOIN guacamole_connection_parameter p
                        ON p.connection_id = c.connection_id
                        AND p.parameter_name IN ('hostname', 'port')
                    GROUP BY c.connection_id, c.connection_name, c.protocol
                    ORDER BY c.connection_id ASC
                    """
                )
            ).mappings().all()
            try:
                user_rows = conn.execute(
                    text(
                        """
                        SELECT
                            cp.connection_id,
                            e.name AS username
                        FROM guacamole_connection_permission cp
                        JOIN guacamole_entity e
                            ON e.entity_id = cp.entity_id
                        WHERE cp.permission = 'READ'
                            AND e.type = 'USER'
                            AND e.name NOT LIKE 'dlabs-res-%'
                        ORDER BY cp.connection_id ASC, e.entity_id ASC
                        """
                    )
                ).mappings().all()
            except Exception as exc:
                logging.warning("Unable to load Guacamole connection users: %s", exc)
                user_rows = []
    except Exception as exc:
        logging.warning("Unable to load Guacamole connections: %s", exc)
        return [], str(exc)

    users_by_connection: Dict[Any, List[str]] = {}
    for row in user_rows:
        connection_id = row.get("connection_id")
        username = str(row.get("username") or "").strip()
        if connection_id is not None and username:
            users_by_connection.setdefault(connection_id, []).append(username)

    return [
        {
            "id": row.get("connection_id"),
            "selector": f"guac:id:{row.get('connection_id')}",
            "name": row.get("connection_name"),
            "protocol": row.get("protocol"),
            "hostname": row.get("hostname"),
            "port": row.get("port"),
            "users": users_by_connection.get(row.get("connection_id"), []),
        }
        for row in rows
    ], None


def require_guacamole_provisioner_auth():
    expected = str(GUACAMOLE_PROVISIONER_TOKEN or "").strip()
    if not expected:
        return None
    provided = request.headers.get(GUACAMOLE_PROVISIONER_TOKEN_HEADER)
    if not provided and GUACAMOLE_PROVISIONER_TOKEN_HEADER.lower() != "x-lab-manager-token":
        provided = request.headers.get("X-Lab-Manager-Token")
    if provided != expected:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


def parse_guacamole_selector(selector: Any) -> int:
    match = GUAC_SELECTOR_RE.match(str(selector or "").strip())
    if not match:
        raise ValueError("selector must use guac:id:<connection_id>")
    return int(match.group(1))


def safe_connection_response(connection: Dict[str, Any]) -> Dict[str, Any]:
    connection_id = connection.get("id")
    return {
        "id": connection_id,
        "selector": connection.get("selector") or f"guac:id:{connection_id}",
        "name": connection.get("name"),
        "protocol": connection.get("protocol"),
        "hostname": connection.get("hostname"),
        "port": connection.get("port"),
        "warnings": [],
    }


def provision_guacamole_temporary_user(
    selector: str,
    session_id: str,
    valid_until_epoch: Optional[Any],
    activate: bool = True,
) -> Dict[str, Any]:
    if not GUACAMOLE_DB_ENGINE:
        raise RuntimeError("Guacamole database not configured")
    connection_id = parse_guacamole_selector(selector)
    if not session_id or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", str(session_id)):
        raise ValueError("sessionId is required and must be a safe identifier")
    username = f"dlabs-res-{session_id}"
    valid_until_date = None
    if valid_until_epoch not in (None, ""):
        valid_until_date = datetime.fromtimestamp(int(valid_until_epoch), tz=timezone.utc).date().isoformat()

    connection = resolve_guacamole_connection(connection_id)
    if not connection:
        raise ValueError(f"Guacamole connection {connection_id} not found")

    with GUACAMOLE_DB_ENGINE.begin() as conn:
        if conn.dialect.name == "mysql":
            conn.execute(
                text(
                    """
                    INSERT INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    ON DUPLICATE KEY UPDATE name = VALUES(name)
                    """
                ),
                {"username": username},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    """
                ),
                {"username": username},
            )

        entity_id = conn.execute(
            text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            raise RuntimeError("Unable to resolve temporary Guacamole entity")

        if conn.dialect.name == "mysql":
            conn.execute(
                text(
                    """
                    INSERT INTO guacamole_user (entity_id, password_hash, password_date, disabled, expired, valid_until)
                    VALUES (:entity_id, UNHEX(SHA2(UUID(), 256)), UTC_TIMESTAMP(), :disabled, FALSE, :valid_until)
                    ON DUPLICATE KEY UPDATE disabled = VALUES(disabled), expired = FALSE, valid_until = VALUES(valid_until)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO guacamole_user (entity_id, valid_until, disabled)
                    VALUES (:entity_id, :valid_until, :disabled)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )

        if activate:
            if conn.dialect.name == "mysql":
                conn.execute(
                    text(
                        """
                        INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        ON DUPLICATE KEY UPDATE permission = VALUES(permission)
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
        else:
            conn.execute(
                text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"),
                {"entity_id": entity_id},
            )

    logging.info("Provisioned temporary Guacamole user %s for connection %s (active=%s)", username, connection_id, activate)
    return {
        "success": True,
        "sessionId": session_id,
        "username": username,
        "connection": safe_connection_response(connection),
    }


def delete_guacamole_temporary_user(session_id: str) -> bool:
    if not GUACAMOLE_DB_ENGINE:
        raise RuntimeError("Guacamole database not configured")
    if not session_id or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", str(session_id)):
        raise ValueError("sessionId is required and must be a safe identifier")
    username = f"dlabs-res-{session_id}"
    with GUACAMOLE_DB_ENGINE.begin() as conn:
        entity_id = conn.execute(
            text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            return False
        conn.execute(text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(text("DELETE FROM guacamole_user WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(text("DELETE FROM guacamole_entity WHERE entity_id = :entity_id"), {"entity_id": entity_id})
    logging.info("Deleted temporary Guacamole user %s", username)
    return True


def cleanup_expired_guacamole_temp_users() -> int:
    if not GUACAMOLE_DB_ENGINE:
        logging.debug("Skipping Guacamole temp user cleanup: database not configured")
        return 0
    try:
        with GUACAMOLE_DB_ENGINE.begin() as conn:
            if conn.dialect.name == "mysql":
                result = conn.execute(
                    text(
                        """
                        DELETE e FROM guacamole_entity e
                        JOIN guacamole_user u ON u.entity_id = e.entity_id
                        WHERE e.type = 'USER'
                          AND e.name LIKE 'dlabs-res-%'
                          AND u.valid_until IS NOT NULL
                          AND u.valid_until < UTC_DATE()
                        """
                    )
                )
            else:
                result = conn.execute(
                    text(
                        """
                        DELETE FROM guacamole_entity
                        WHERE entity_id IN (
                            SELECT e.entity_id
                            FROM guacamole_entity e
                            JOIN guacamole_user u ON u.entity_id = e.entity_id
                            WHERE e.type = 'USER'
                              AND e.name LIKE 'dlabs-res-%'
                              AND u.valid_until IS NOT NULL
                              AND u.valid_until < CURRENT_DATE
                        )
                        """
                    )
                )
        deleted = result.rowcount if result.rowcount is not None else 0
        if deleted:
            logging.info("Cleaned up %s expired Guacamole temporary users", deleted)
        return deleted
    except Exception as exc:
        logging.warning("Guacamole temp user cleanup failed: %s", exc)
        return 0


def build_host_inventory() -> Dict[str, Any]:
    with HOSTS_LOCK:
        hosts = HOSTS.all_hosts()
    guacamole_connections, guacamole_error = load_guacamole_connections()
    claimed_ids = set()
    host_entries = []

    for host in hosts:
        match_keys = {
            normalize_match_key(host.get("name")),
            normalize_match_key(host.get("address")),
        }
        match_keys.discard("")
        matches = [
            conn for conn in guacamole_connections
            if normalize_match_key(conn.get("hostname")) in match_keys
        ]
        for conn in matches:
            claimed_ids.add(conn.get("id"))

        if len(matches) == 1:
            status = "linked"
        elif len(matches) > 1:
            status = "ambiguous"
        else:
            status = "missing"

        entry = safe_host_inventory_entry(host)
        entry["guacamole"] = {
            "status": status,
            "connections": matches,
        }
        host_entries.append(entry)

    unmatched = [
        conn for conn in guacamole_connections
        if conn.get("id") not in claimed_ids
    ]

    return {
        "hosts": host_entries,
        "guacamoleAvailable": guacamole_error is None,
        "guacamoleError": guacamole_error,
        "guacamoleUnmatched": unmatched,
    }


@APP.route("/api/hosts", methods=["GET"])
def api_hosts_inventory():
    return jsonify(build_host_inventory())


@APP.route("/internal/guacamole/connections", methods=["GET"])
def api_internal_guacamole_connections():
    auth_response = require_guacamole_provisioner_auth()
    if auth_response:
        return auth_response
    connections, error = load_guacamole_connections()
    if error:
        return jsonify({"success": False, "error": error}), 503
    return jsonify({
        "success": True,
        "connections": [safe_connection_response(connection) for connection in connections],
    })


@APP.route("/internal/guacamole/provision", methods=["POST"])
def api_internal_guacamole_provision():
    auth_response = require_guacamole_provisioner_auth()
    if auth_response:
        return auth_response
    payload = request.get_json(silent=True) or {}
    try:
        activate = payload.get("activate", True)
        if not isinstance(activate, bool):
            raise ValueError("activate must be a boolean")
        result = provision_guacamole_temporary_user(
            str(payload.get("selector") or "").strip(),
            str(payload.get("sessionId") or "").strip(),
            payload.get("validUntilEpochSeconds"),
            activate,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Guacamole provisioning failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@APP.route("/internal/guacamole/provision/<session_id>", methods=["DELETE"])
def api_internal_guacamole_delete(session_id: str):
    auth_response = require_guacamole_provisioner_auth()
    if auth_response:
        return auth_response
    try:
        deleted = delete_guacamole_temporary_user(session_id)
        return jsonify({"success": True, "deleted": deleted, "sessionId": session_id})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Guacamole temporary-user cleanup failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@APP.route("/api/hosts/discover", methods=["POST"])
def api_hosts_discover():
    payload = request.get_json(force=True, silent=True) or {}
    connection_id = payload.get("connectionId") or payload.get("connection_id")
    if connection_id in (None, ""):
        return jsonify({"error": "connectionId is required"}), 400

    connection = resolve_guacamole_connection(connection_id)
    if not connection:
        return jsonify({"error": f"Guacamole connection {connection_id} not found"}), 404

    return jsonify(discover_labstation_candidate(connection))


@APP.route("/api/hosts/provision", methods=["POST"])
def api_hosts_provision():
    payload = request.get_json(force=True, silent=True) or {}
    connection_id = payload.get("connectionId") or payload.get("connection_id")
    if connection_id in (None, ""):
        return jsonify({"error": "connectionId is required"}), 400

    connection = resolve_guacamole_connection(connection_id)
    if not connection:
        return jsonify({"error": f"Guacamole connection {connection_id} not found"}), 404

    discovery = discover_labstation_candidate(connection)
    if discovery.get("status") not in ENOUGH_DISCOVERY_SIGNALS:
        return jsonify({
            "error": "insufficient discovery signal for ops host provisioning",
            "discovery": discovery,
        }), 409

    provision_payload = dict(payload)
    if not str(provision_payload.get("mac") or "").strip():
        ops_host_draft = discovery.get("opsHostDraft")
        suggested_mac = ops_host_draft.get("mac") if isinstance(ops_host_draft, dict) else None
        if suggested_mac:
            provision_payload["mac"] = suggested_mac

    host_config, error = build_provisioned_host(provision_payload, connection)
    if error:
        return jsonify({"error": error}), 400
    if host_config is None:
        return jsonify({"error": "host configuration could not be built"}), 400

    existing = HOSTS.get(host_config["name"])
    if existing:
        return jsonify({"error": f"host {host_config['name']} already exists"}), 409

    try:
        upsert_dynamic_host(host_config)
        count, reload_error = reload_hosts()
    except Exception as exc:
        logging.exception("Failed to provision ops host")
        return jsonify({"error": str(exc)}), 500

    if reload_error:
        return jsonify({"error": reload_error}), 500

    return jsonify({
        "provisioned": True,
        "hosts": count,
        "host": safe_host_inventory_entry(host_config),
        "discoveryStatus": discovery.get("status"),
    })


@APP.route("/api/hosts/winrm-credentials", methods=["POST"])
def api_save_winrm_credentials():
    payload = request.get_json(force=True, silent=True) or {}
    credential_ref = payload.get("credentialRef") or payload.get("credential_ref")
    user = payload.get("user") or payload.get("username")
    password = payload.get("password")
    try:
        save_winrm_credentials(str(credential_ref or ""), str(user or ""), str(password or ""))
        count, reload_error = reload_hosts()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Failed to save WinRM credentials")
        return jsonify({"error": str(exc)}), 500
    if reload_error:
        return jsonify({"error": reload_error}), 500
    return jsonify({
        "saved": True,
        "credentialRef": normalize_credential_ref(credential_ref),
        "hosts": count,
    })


@APP.route("/api/hosts/reload", methods=["POST"])
def api_hosts_reload():
    count, error = reload_hosts()
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"reloaded": True, "hosts": count})


@APP.route("/api/aas-sync", methods=["POST"])
def api_aas_sync():
    """
    Sync AAS shells for all labs mapped to the given host.

    This is a convenience wrapper over /aas-admin/lab/<lab_id>/sync for the
    lab-manager UI, which knows hosts by name but not individual lab IDs.
    Protected at OpenResty via LAB_MANAGER_TOKEN (same as /ops/api/*).

    Request body: { "host": "<host-name>" }
    Response: { "host": "...", "labs": [{ "labId": "1", "synced": true, ... }] }
    """
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    labs = host.get("labs", [])
    if not labs:
        return jsonify({"host": host_name, "labs": [], "message": "No labs mapped to this host"}), 200
    results = []
    for lab_id in labs:
        try:
            result = aas_generator.sync_lab_to_basyx(str(lab_id), host)
            results.append({"labId": str(lab_id), **result})
        except Exception as exc:  # pylint: disable=broad-except
            results.append({"labId": str(lab_id), "error": str(exc)})
    return jsonify({"host": host_name, "labs": results}), 200


@APP.route("/api/hosts/quarantine", methods=["POST"])
def api_hosts_quarantine():
    payload = request.get_json(silent=True) or {}
    name = payload.get("host") or payload.get("name")
    quarantined = parse_bool(payload.get("quarantined"), True)
    if not name:
        return jsonify({"error": "host is required"}), 400
    with HOSTS_LOCK:
        ok = HOSTS.set_quarantine(name, quarantined)
    if not ok:
        return jsonify({"error": f"host {name} not found"}), 404
    return jsonify({"host": name, "quarantined": quarantined})


@APP.route("/api/hosts/local-mode", methods=["POST"])
def api_hosts_local_mode():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    if host_name is None:
        return jsonify({"error": "host is required"}), 400
    enabled = payload.get("enabled")
    if enabled is None:
        return jsonify({"error": "enabled is required"}), 400
    enabled = parse_bool(enabled, False)

    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404

    flag_path = get_local_mode_flag_path(host)
    try:
        if enabled:
            write_remote_file(host, flag_path, "1", None, None, None, None, None)
        else:
            remove_remote_file(host, flag_path, None, None, None, None, None)
    except Exception as exc:
        logging.exception("Local mode toggle failed for %s", host_name)
        return jsonify({"error": str(exc)}), 500

    return jsonify({"host": host_name, "localModeEnabled": enabled}), 200


@APP.route("/api/operations/recent", methods=["GET"])
def api_operations_recent():
    if not DB_ENGINE:
        return jsonify({"error": "Database not configured"}), 500
    limit = _sanitize_limit(request.args.get("limit"))
    offset = _sanitize_offset(request.args.get("offset"))
    host_name = request.args.get("host")
    reservation_id = request.args.get("reservationId") or request.args.get("reservation_id")

    query_base = "FROM reservation_operations"
    params: Dict[str, Any] = {}
    where_clauses: List[str] = []
    if host_name:
        host = HOSTS.get(host_name)
        if not host:
            return jsonify({"error": f"host '{host_name}' not found"}), 404
        where_clauses.append("host = :host")
        params["host"] = host_name
    if reservation_id:
        where_clauses.append("reservation_id = :reservation_id")
        params["reservation_id"] = reservation_id

    if where_clauses:
        query_base += " WHERE " + " AND ".join(where_clauses)

    params["limit_value"] = limit
    params["offset_value"] = offset
    try:
        with DB_ENGINE.begin() as conn:
            total = conn.execute(text("SELECT COUNT(*) as total " + query_base), params).scalar() or 0
            rows = conn.execute(
                text(
                    "SELECT reservation_id, lab_id, host, action, status, success, message, payload, response_code, duration_ms, created_at "
                    + query_base
                    + " ORDER BY created_at DESC, id DESC LIMIT :limit_value OFFSET :offset_value"
                ),
                params,
            ).mappings().all()
        returned = len(rows)
        pagination = {
            "limit": limit,
            "offset": offset,
            "returned": returned,
            "total": total,
            "nextOffset": offset + returned,
            "hasMore": total > offset + returned,
            "page": (offset // limit) + 1 if limit else 1,
            "pageSize": limit,
        }
        return jsonify({"operations": _rows_to_operations([dict(row) for row in rows]), "pagination": pagination})
    except Exception as exc:
        logging.exception("Failed to load recent operations")
        return jsonify({"error": str(exc)}), 500


@APP.route("/aas-admin/lab/<lab_id>/sync", methods=["POST"])
def api_aas_sync_lab(lab_id: str):
    """
    Sync (create or update) the AAS shell and submodels for a physical lab resource.

    This endpoint is protected at the OpenResty layer via lab_manager_admin_access.lua
    and is only available on Full Gateway instances (--profile aas).

    Optional JSON body:
      { "includeHeartbeat": true }  — polls fresh heartbeat before syncing (default: false)

    The host is resolved from the lab_id via the HOSTS registry.
    If the lab_id is not mapped, returns 404.
    """
    host = HOSTS.get_by_lab(lab_id)
    if not host:
        # Try without quarantine filter (quarantined labs can still have their AAS updated)
        host = HOSTS.lab_index.get(str(lab_id).strip().lower()) if hasattr(HOSTS, "lab_index") else None
    if not host:
        return jsonify({"error": f"No host mapping found for labId '{lab_id}'"}), 404

    payload = request.get_json(silent=True) or {}
    include_heartbeat = parse_bool(payload.get("includeHeartbeat", False), False)

    heartbeat_data: Optional[Dict[str, Any]] = None
    if include_heartbeat:
        try:
            poll_result = poll_heartbeat(host, include_events=False)
            heartbeat_data = poll_result.get("heartbeat")
        except Exception as exc:
            logging.warning("AAS sync: could not poll heartbeat for lab %s: %s", lab_id, exc)
    elif DB_ENGINE:
        # Use latest persisted heartbeat from DB if available
        try:
            with DB_ENGINE.begin() as conn:
                heartbeat_data_row = _fetch_latest_heartbeat(conn, host.get("name", ""))
                if heartbeat_data_row and heartbeat_data_row.get("raw"):
                    heartbeat_data = heartbeat_data_row["raw"]
        except Exception as exc:
            logging.warning("AAS sync: could not load heartbeat from DB for lab %s: %s", lab_id, exc)

    result = aas_generator.sync_lab_to_basyx(str(lab_id), host, heartbeat_data)

    if result.get("disabled"):
        return jsonify(result), 200

    if result.get("error"):
        return jsonify({"detail": result["error"], **result}), 502

    return jsonify(result), 200


def poll_all_hosts():
    for host in HOSTS.all_hosts():
        try:
            poll_heartbeat(host, include_events=True)
            logging.info("Polled heartbeat for %s", host.get("name"))
        except Exception as exc:
            logging.error("Heartbeat poll failed for %s: %s", host.get("name"), exc)


class ReservationOrchestrator:
    def __init__(self, engine: Optional[Engine], registry: HostRegistry):
        self.engine = engine
        self.registry = registry
        self.enabled = parse_bool(os.getenv("OPS_RESERVATION_AUTOMATION", False), False)
        self.scan_interval = int(os.getenv("OPS_RESERVATION_SCAN_INTERVAL", "30"))
        self.start_lead = int(os.getenv("OPS_RESERVATION_START_LEAD", "120"))
        self.end_delay = int(os.getenv("OPS_RESERVATION_END_DELAY", "60"))
        self.lookback = int(os.getenv("OPS_RESERVATION_LOOKBACK", "21600"))  # 6 hours
        self.retry_cooldown = int(os.getenv("OPS_RESERVATION_RETRY_COOLDOWN", "60"))

    def register(self, scheduler: BackgroundScheduler) -> int:
        if not self.enabled:
            logging.info("Reservation orchestrator disabled (OPS_RESERVATION_AUTOMATION=false)")
            return 0
        if not self.engine:
            logging.warning("Reservation orchestrator disabled: ops database DSN is not configured")
            return 0
        scheduler.add_job(
            self.scan_once,
            "interval",
            seconds=self.scan_interval,
            next_run_time=datetime.now(timezone.utc),
            id="reservation-orchestrator",
            replace_existing=True,
        )
        logging.info(
            "Reservation orchestrator enabled (scan=%ss, lead=%ss, end_delay=%ss)",
            self.scan_interval,
            self.start_lead,
            self.end_delay,
        )
        return 1

    def scan_once(self):
        if not self.enabled or not self.engine:
            return
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as conn:
                start_rows = self._fetch_start_candidates(conn, now)
                end_rows = self._fetch_end_candidates(conn, now)
        except Exception as exc:
            logging.error("Reservation orchestrator query failed: %s", exc)
            return

        for row in start_rows:
            self._dispatch_start(dict(row))
        for row in end_rows:
            self._dispatch_end(dict(row))

    def _fetch_start_candidates(self, conn: Connection, now: datetime):
        if conn.dialect.name == "mysql":
            conn.execute(text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        window_upper = now + timedelta(seconds=self.start_lead)
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(os.getenv("OPS_RESERVATION_MAX_BATCH", "200"))
        query = text(
            """
            SELECT transaction_hash, lab_id, start_time, end_time, status
            FROM lab_reservations r
            WHERE r.status = 'CONFIRMED'
              AND r.start_time <= :window_upper
              AND r.start_time >= :window_lower
              AND NOT EXISTS (
                  SELECT 1 FROM reservation_operations o
                  WHERE o.reservation_id = r.transaction_hash
                    AND o.action = 'scheduler:start'
                    AND o.created_at >= :retry_cutoff
              )
            ORDER BY r.start_time ASC
            LIMIT :max_batch
            """
        )
        result = conn.execute(
            query,
            {
                "window_upper": window_upper,
                "window_lower": window_lower,
                "retry_cutoff": retry_cutoff,
                "max_batch": max_batch,
            },
        )
        return result.mappings().all()

    def _fetch_end_candidates(self, conn: Connection, now: datetime):
        if conn.dialect.name == "mysql":
            conn.execute(text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        ready_time = now - timedelta(seconds=self.end_delay)
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(os.getenv("OPS_RESERVATION_MAX_BATCH", "200"))
        query = text(
            """
            SELECT transaction_hash, lab_id, start_time, end_time, status
            FROM lab_reservations r
            WHERE r.status IN ('CONFIRMED','ACTIVE')
              AND r.end_time <= :ready_time
              AND r.end_time >= :window_lower
              AND NOT EXISTS (
                  SELECT 1 FROM reservation_operations o
                  WHERE o.reservation_id = r.transaction_hash
                    AND o.action = 'scheduler:end'
                    AND o.created_at >= :retry_cutoff
              )
            ORDER BY r.end_time ASC
            LIMIT :max_batch
            """
        )
        result = conn.execute(
            query,
            {
                "ready_time": ready_time,
                "window_lower": window_lower,
                "retry_cutoff": retry_cutoff,
                "max_batch": max_batch,
            },
        )
        return result.mappings().all()

    def _dispatch_start(self, row: Mapping[str, Any]):
        reservation_id = row["transaction_hash"]
        lab_id = row.get("lab_id")
        host = self.registry.get_by_lab(lab_id)
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            logging.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "start", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        response, status_code = handle_reservation_start(payload)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation start failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            "start",
            success,
            message,
            payload={"response": response, "status_code": status_code},
            response_code=status_code,
        )
        if success:
            self._update_status(reservation_id, row.get("status"), "ACTIVE")

    def _dispatch_end(self, row: Mapping[str, Any]):
        reservation_id = row["transaction_hash"]
        lab_id = row.get("lab_id")
        host = self.registry.get_by_lab(lab_id)
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            logging.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "end", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        response, status_code = handle_reservation_end(payload)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation end failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            "end",
            success,
            message,
            payload={"response": response, "status_code": status_code},
            response_code=status_code,
        )
        if success:
            self._update_status(reservation_id, row.get("status"), "COMPLETED")

    def _record_scheduler_op(
        self,
        reservation_id: str,
        lab_id: Optional[Any],
        host_name: str,
        action_suffix: str,
        success: bool,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        response_code: Optional[int] = None,
    ):
        status = "completed" if success else "failed"
        record_reservation_operation(
            reservation_id,
            str(lab_id) if lab_id is not None else None,
            host_name,
            f"scheduler:{action_suffix}",
            status,
            success,
            response_code=response_code,
            payload=payload,
            message=message,
        )

    def _update_status(self, reservation_id: str, current_status: Optional[str], new_status: str):
        if not self.engine or not current_status:
            return
        allowed = {
            ("CONFIRMED", "ACTIVE"),
            ("CONFIRMED", "COMPLETED"),
            ("ACTIVE", "COMPLETED"),
            ("CONFIRMED", "CANCELLED"),
            ("ACTIVE", "CANCELLED"),
        }
        if (current_status, new_status) not in allowed:
            logging.debug(
                "Skipping status transition %s -> %s for %s (not allowed)",
                current_status,
                new_status,
                reservation_id,
            )
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE lab_reservations
                        SET status=:new_status, updated_at=UTC_TIMESTAMP()
                        WHERE transaction_hash=:reservation_id AND status=:current_status
                        """
                    ),
                    {
                        "reservation_id": reservation_id,
                        "current_status": current_status,
                        "new_status": new_status,
                    },
                )
        except Exception as exc:
            logging.error(
                "Failed to update reservation %s status to %s: %s",
                reservation_id,
                new_status,
                exc,
            )


RESERVATION_AUTOMATOR = ReservationOrchestrator(DB_ENGINE, HOSTS)


def session_observation_retry_delay_seconds(attempts: int) -> int:
    return min(300, 5 * (2 ** min(max(0, attempts - 1), 6)))


def _encrypt_runtime_secret(value: str) -> str:
    return _load_or_create_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt_runtime_secret(value: str) -> str:
    return _load_or_create_fernet().decrypt(value.encode("ascii")).decode("utf-8")


def enqueue_guacamole_token_revocation(payload: Mapping[str, Any]) -> bool:
    if not DB_ENGINE:
        return False
    required = ("authToken", "username", "reservationKey", "jwtJti", "gatewayId", "expiresAt")
    if any(not str(payload.get(field) or "").strip() for field in required):
        return False
    token = str(payload["authToken"]).strip()
    if len(token) > 512:
        return False
    try:
        expires_at = datetime.fromtimestamp(int(payload["expiresAt"]), tz=timezone.utc).replace(tzinfo=None)
        ciphertext = _encrypt_runtime_secret(token)
    except (TypeError, ValueError, OverflowError):
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    values = {
        "token_hash": token_hash,
        "token_ciphertext": ciphertext,
        "username": str(payload["username"]).strip().lower(),
        "reservation_key": str(payload["reservationKey"]).strip(),
        "jwt_jti": str(payload["jwtJti"]).strip(),
        "gateway_id": str(payload["gatewayId"]).strip(),
        "expires_at": expires_at,
    }
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(text("""
                INSERT INTO guacamole_token_revocation_queue (
                    token_hash, token_ciphertext, username, reservation_key,
                    jwt_jti, gateway_id, expires_at, status, next_attempt_at
                ) VALUES (
                    :token_hash, :token_ciphertext, :username, :reservation_key,
                    :jwt_jti, :gateway_id, :expires_at, 'PENDING', CURRENT_TIMESTAMP
                )
            """), values)
        return True
    except IntegrityError:
        try:
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET token_ciphertext = :token_ciphertext,
                        username = :username,
                        reservation_key = :reservation_key,
                        jwt_jti = :jwt_jti,
                        gateway_id = :gateway_id,
                        expires_at = :expires_at,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash AND status != 'REVOKED'
                """), values)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Guacamole revocation duplicate recovery failed: %s", exc)
            return False
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Guacamole revocation ingest failed: %s", exc)
        return False


def ingest_guacamole_revocation_spool() -> int:
    """Move crash-safe Lua spool entries into the encrypted MySQL queue."""
    spool = Path(GUAC_REVOCATION_SPOOL_DIR)
    if not spool.is_dir():
        return 0
    ingested = 0
    for entry in sorted(spool.glob("*.json")):
        try:
            if entry.stat().st_size > 16 * 1024:
                logging.error("Deleting oversized Guacamole revocation spool entry %s", entry.name)
                entry.unlink(missing_ok=True)
                continue
            payload = json.loads(entry.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and enqueue_guacamole_token_revocation(payload):
                entry.unlink(missing_ok=True)
                ingested += 1
            elif not isinstance(payload, dict):
                entry.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError) as exc:
            logging.warning("Unable to ingest Guacamole revocation spool entry %s: %s", entry.name, exc)
    return ingested


@APP.route("/internal/guacamole-token-revocations", methods=["POST"])
def ingest_guacamole_token_revocation():
    if not SESSION_OBSERVATION_INGEST_TOKEN:
        return jsonify({"accepted": False, "error": "Guacamole revocation ingestion is disabled"}), 503
    provided = request.headers.get("X-Gateway-Observation-Token", "")
    if not hmac.compare_digest(provided, SESSION_OBSERVATION_INGEST_TOKEN):
        return jsonify({"accepted": False, "error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not enqueue_guacamole_token_revocation(payload):
        return jsonify({"accepted": False, "error": "invalid or unavailable revocation"}), 400
    return jsonify({"accepted": True}), 202


def _guacamole_admin_session() -> Optional[Tuple[str, str]]:
    if not GUAC_ADMIN_USER or not GUAC_ADMIN_PASS:
        return None
    response = requests.post(
        f"{GUAC_API_URL}/tokens",
        data={"username": GUAC_ADMIN_USER, "password": GUAC_ADMIN_PASS},
        timeout=5,
    )
    if response.status_code != 200:
        return None
    body = response.json()
    token = str(body.get("authToken") or "").strip()
    data_source = str(body.get("dataSource") or "mysql").strip()
    return (token, data_source) if token else None


def _reconcile_guacamole_observations(admin_token: str, data_source: str) -> None:
    if not DB_ENGINE:
        return
    response = requests.get(
        f"{GUAC_API_URL}/session/data/{quote(data_source, safe='')}/activeConnections",
        params={"token": admin_token},
        timeout=5,
    )
    if response.status_code != 200:
        return
    active_users = {
        str(connection.get("username") or "").strip().lower()
        for connection in (response.json() or {}).values()
        if isinstance(connection, dict)
    }
    if not active_users:
        return
    with DB_ENGINE.begin() as conn:
        rows = conn.execute(text("""
            SELECT token_hash, reservation_key, jwt_jti, gateway_id, username
            FROM guacamole_token_revocation_queue
            WHERE status IN ('PENDING', 'RETRY')
              AND observed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at ASC
            LIMIT 100
        """)).mappings().all()
    for row in rows:
        if str(row["username"]).lower() not in active_users:
            continue
        accepted = enqueue_session_observation({
            "dedupKey": row["token_hash"],
            "reservationKey": row["reservation_key"],
            "jwtJti": row["jwt_jti"],
            "sessionId": f"guac:{row['token_hash']}",
            "gatewayId": row["gateway_id"],
            "accessType": "guacamole",
            "observedAt": int(time.time()),
        })
        if accepted:
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET observed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash AND observed_at IS NULL
                """), {"token_hash": row["token_hash"]})


def process_guacamole_token_revocations() -> int:
    ingest_guacamole_revocation_spool()
    if not DB_ENGINE:
        return 0
    session = _guacamole_admin_session()
    if not session:
        logging.warning("Guacamole token revocation deferred: admin session unavailable")
        return 0
    admin_token, data_source = session
    try:
        _reconcile_guacamole_observations(admin_token, data_source)
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Guacamole session observation reconciliation failed: %s", exc)
    with DB_ENGINE.begin() as conn:
        rows = conn.execute(text("""
            SELECT token_hash, token_ciphertext, attempts
            FROM guacamole_token_revocation_queue
            WHERE status IN ('PENDING', 'RETRY')
              AND expires_at <= CURRENT_TIMESTAMP
              AND next_attempt_at <= CURRENT_TIMESTAMP
            ORDER BY expires_at ASC
            LIMIT 100
        """)).mappings().all()
    revoked = 0
    for row in rows:
        attempts = int(row["attempts"] or 0) + 1
        try:
            user_token = _decrypt_runtime_secret(str(row["token_ciphertext"]))
            response = requests.delete(
                f"{GUAC_API_URL}/tokens/{quote(user_token, safe='')}",
                params={"token": admin_token},
                timeout=5,
            )
            if response.status_code not in (204, 404):
                raise RuntimeError(f"Guacamole token delete returned {response.status_code}")
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET status = 'REVOKED', attempts = :attempts,
                        revoked_at = CURRENT_TIMESTAMP, last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash
                """), {"token_hash": row["token_hash"], "attempts": attempts})
            revoked += 1
        except Exception as exc:  # pylint: disable=broad-except
            status = "FAILED" if attempts >= GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS else "RETRY"
            next_attempt = datetime.now(timezone.utc) + timedelta(
                seconds=session_observation_retry_delay_seconds(attempts)
            )
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET status = :status, attempts = :attempts,
                        next_attempt_at = :next_attempt_at, last_error = :last_error,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash
                """), {
                    "status": status,
                    "attempts": attempts,
                    "next_attempt_at": next_attempt,
                    "last_error": str(exc)[:1024],
                    "token_hash": row["token_hash"],
                })
    return revoked


def enqueue_session_observation(payload: Mapping[str, Any]) -> bool:
    """Persist an OpenResty WebSocket-open observation before it is delivered."""
    if not DB_ENGINE:
        return False
    required_fields = (
        "dedupKey", "reservationKey", "jwtJti", "sessionId", "gatewayId", "accessType", "observedAt",
    )
    if any(not str(payload.get(field) or "").strip() for field in required_fields):
        return False
    try:
        observed_at = datetime.fromtimestamp(int(payload["observedAt"]), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return False
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO gateway_session_observation_outbox (
                        dedup_key, reservation_key, jwt_jti, session_id, gateway_id,
                        access_type, observed_at, status, next_attempt_at
                    ) VALUES (
                        :dedup_key, :reservation_key, :jwt_jti, :session_id, :gateway_id,
                        :access_type, :observed_at, 'PENDING', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "dedup_key": str(payload["dedupKey"]).strip(),
                    "reservation_key": str(payload["reservationKey"]).strip(),
                    "jwt_jti": str(payload["jwtJti"]).strip(),
                    "session_id": str(payload["sessionId"]).strip(),
                    "gateway_id": str(payload["gatewayId"]).strip(),
                    "access_type": str(payload["accessType"]).strip().lower(),
                    "observed_at": observed_at,
                },
            )
        return True
    except IntegrityError:
        # A repeated WebSocket observation is idempotent. A terminal delivery
        # is reopened only when the trusted gateway observes the same session again.
        try:
            with DB_ENGINE.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE gateway_session_observation_outbox
                        SET status = CASE WHEN status = 'FAILED' THEN 'RETRY' ELSE status END,
                            attempts = CASE WHEN status = 'FAILED' THEN 0 ELSE attempts END,
                            next_attempt_at = CASE
                                WHEN status IN ('FAILED', 'RETRY') THEN CURRENT_TIMESTAMP
                                ELSE next_attempt_at
                            END,
                            locked_at = CASE WHEN status = 'FAILED' THEN NULL ELSE locked_at END,
                            last_error = CASE WHEN status = 'FAILED' THEN NULL ELSE last_error END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE dedup_key = :dedup_key
                        """
                    ),
                    {"dedup_key": str(payload["dedupKey"]).strip()},
                )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Session observation duplicate recovery failed: %s", exc)
            return False
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Session observation outbox ingest failed: %s", exc)
        return False


@APP.route("/internal/session-observations", methods=["POST"])
def ingest_session_observation():
    """Accept observations only from the co-located OpenResty gateway."""
    if not SESSION_OBSERVATION_INGEST_TOKEN:
        return jsonify({"accepted": False, "error": "session observation ingestion is disabled"}), 503
    provided = request.headers.get("X-Gateway-Observation-Token", "")
    if not hmac.compare_digest(provided, SESSION_OBSERVATION_INGEST_TOKEN):
        return jsonify({"accepted": False, "error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not enqueue_session_observation(payload):
        return jsonify({"accepted": False, "error": "invalid or unavailable observation"}), 400
    return jsonify({"accepted": True}), 202


def _claim_session_observation_outbox_rows() -> List[Dict[str, Any]]:
    if not DB_ENGINE:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE gateway_session_observation_outbox
                    SET status = 'RETRY', next_attempt_at = CURRENT_TIMESTAMP,
                        locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'SENDING' AND locked_at < :cutoff
                    """
                ),
                {"cutoff": cutoff},
            )
            rows = conn.execute(
                text(
                    """
                    SELECT id, reservation_key, jwt_jti, session_id, gateway_id,
                           access_type, observed_at, attempts
                    FROM gateway_session_observation_outbox
                    WHERE status IN ('PENDING', 'RETRY')
                      AND next_attempt_at <= CURRENT_TIMESTAMP
                    ORDER BY next_attempt_at ASC, id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": SESSION_OBSERVATION_OUTBOX_BATCH_SIZE},
            ).mappings().all()
            claimed = []
            for row in rows:
                updated = conn.execute(
                    text(
                        """
                        UPDATE gateway_session_observation_outbox
                        SET status = 'SENDING', locked_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id AND status IN ('PENDING', 'RETRY')
                        """
                    ),
                    {"id": row["id"]},
                ).rowcount
                if updated == 1:
                    claimed.append(dict(row))
            return claimed
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Session observation outbox claim failed: %s", exc)
        return []


def _mark_session_observation_delivered(record_id: int) -> None:
    if not DB_ENGINE:
        return
    with DB_ENGINE.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gateway_session_observation_outbox
                SET status = 'SENT', delivered_at = CURRENT_TIMESTAMP,
                    locked_at = NULL, last_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'SENDING'
                """
            ),
            {"id": record_id},
        )


def _mark_session_observation_failure(record: Mapping[str, Any], error: str) -> None:
    if not DB_ENGINE:
        return
    attempts = int(record.get("attempts") or 0) + 1
    status = "FAILED" if attempts >= SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS else "RETRY"
    next_attempt = datetime.now(timezone.utc) + timedelta(
        seconds=session_observation_retry_delay_seconds(attempts)
    )
    with DB_ENGINE.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gateway_session_observation_outbox
                SET status = :status, attempts = :attempts,
                    next_attempt_at = :next_attempt_at, locked_at = NULL,
                    last_error = :last_error, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'SENDING'
                """
            ),
            {
                "id": record["id"],
                "status": status,
                "attempts": attempts,
                "next_attempt_at": next_attempt,
                "last_error": str(error)[:1024],
            },
        )


def _session_observed_epoch(value: Any) -> int:
    if isinstance(value, datetime):
        return int((value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp())
    parsed = to_utc(value)
    if parsed:
        return int(parsed.timestamp())
    return int(time.time())


def _base64url_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _session_observer_authorization() -> str:
    """Create a short-lived JWT scoped only to session-observation submission."""
    if not SESSION_OBSERVER_GATEWAY_ID or not SESSION_OBSERVER_SIGNING_SECRET:
        raise RuntimeError("session observer gateway credentials are not configured")
    padding = "=" * (-len(SESSION_OBSERVER_SIGNING_SECRET) % 4)
    key = base64.urlsafe_b64decode(SESSION_OBSERVER_SIGNING_SECRET + padding)
    if len(key) < 32:
        raise RuntimeError("session observer signing secret must contain at least 32 bytes")
    now = int(time.time())
    header = _base64url_json({"alg": "HS256", "typ": "JWT"})
    payload = _base64url_json({
        "iss": SESSION_OBSERVER_GATEWAY_ID,
        "sub": SESSION_OBSERVER_GATEWAY_ID,
        "aud": "session-observation",
        "scope": "session-observation:submit",
        "iat": now,
        "exp": now + 60,
        "jti": base64.urlsafe_b64encode(os.urandom(18)).rstrip(b"=").decode("ascii"),
    })
    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return f"Bearer {signing_input}.{signature}"


def deliver_session_observation_outbox() -> int:
    """Deliver durable WebSocket-open observations to blockchain-services."""
    if not SESSION_OBSERVATION_OUTBOX_ENABLED or not DB_ENGINE:
        return 0
    if not ACCESS_AUDIT_URL:
        logging.error("Session observation outbox is pending: ACCESS_AUDIT_URL must target the issuing Full gateway")
        return 0
    if not SESSION_OBSERVER_GATEWAY_ID or not SESSION_OBSERVER_SIGNING_SECRET:
        logging.error("Session observation outbox is pending: session observer credentials are not configured")
        return 0

    delivered = 0
    for record in _claim_session_observation_outbox_rows():
        payload = {
            "reservationKey": record["reservation_key"],
            "jwtJti": record["jwt_jti"],
            "sessionId": record["session_id"],
            "gatewayId": SESSION_OBSERVER_GATEWAY_ID,
            "accessType": record["access_type"],
            "observedAt": _session_observed_epoch(record["observed_at"]),
        }
        try:
            response = requests.post(
                ACCESS_AUDIT_URL,
                json=payload,
                headers={"Authorization": _session_observer_authorization()},
                timeout=SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS,
            )
            body = response.json() if response.content else {}
            if 200 <= response.status_code < 300 and body.get("recorded") is True:
                _mark_session_observation_delivered(record["id"])
                delivered += 1
            else:
                _mark_session_observation_failure(
                    record,
                    f"audit endpoint status={response.status_code} recorded={body.get('recorded')!r}",
                )
        except Exception as exc:  # pylint: disable=broad-except
            _mark_session_observation_failure(record, f"audit delivery failed: {exc}")
    return delivered


def reload_hosts() -> Tuple[int, Optional[str]]:
    """Reload host catalog from CONFIG_PATH."""
    global HOSTS
    try:
        cfg = load_config()
        registry = HostRegistry(cfg)
        with HOSTS_LOCK:
            HOSTS = registry
            RESERVATION_AUTOMATOR.registry = registry
        logging.info("Reloaded hosts catalog (%s hosts)", registry.count())
        return registry.count(), None
    except Exception as exc:
        logging.error("Failed to reload hosts: %s", exc)
        return 0, str(exc)


def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    jobs = 0

    if os.getenv("OPS_POLL_ENABLED", "false").lower() == "true":
        interval = int(os.getenv("OPS_POLL_INTERVAL", "60"))
        scheduler.add_job(
            poll_all_hosts,
            "interval",
            seconds=interval,
            next_run_time=datetime.now(timezone.utc),
            id="heartbeat-poller",
            replace_existing=True,
        )
        jobs += 1
        logging.info("Heartbeat poller enabled (interval %ss)", interval)

    jobs += RESERVATION_AUTOMATOR.register(scheduler)

    if GUACAMOLE_TEMP_USER_CLEANUP_ENABLED:
        scheduler.add_job(
            cleanup_expired_guacamole_temp_users,
            "interval",
            seconds=GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS,
            next_run_time=datetime.now(timezone.utc),
            id="guacamole-temp-user-cleanup",
            replace_existing=True,
        )
        jobs += 1
        logging.info(
            "Guacamole temporary user cleanup enabled (interval %ss)",
            GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS,
        )

    if SESSION_OBSERVATION_OUTBOX_ENABLED:
        scheduler.add_job(
            deliver_session_observation_outbox,
            "interval",
            seconds=SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS,
            next_run_time=datetime.now(timezone.utc),
            id="session-observation-outbox",
            replace_existing=True,
        )
        jobs += 1
        logging.info(
            "Session observation outbox enabled (interval %ss)",
            SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS,
        )

    scheduler.add_job(
        process_guacamole_token_revocations,
        "interval",
        seconds=GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS,
        next_run_time=datetime.now(timezone.utc),
        id="guacamole-token-revocation",
        replace_existing=True,
    )
    jobs += 1
    logging.info(
        "Durable Guacamole token revocation enabled (interval %ss)",
        GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS,
    )

    if jobs == 0:
        logging.info("Scheduler not started (no jobs enabled)")
        return

    scheduler.start()
    logging.info("Scheduler started with %s job(s)", jobs)


def configure_logging():
    level = os.getenv("OPS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def main():
    configure_logging()
    start_scheduler()
    bind = os.getenv("OPS_BIND", "0.0.0.0")
    port = int(os.getenv("OPS_PORT", "8081"))
    APP.run(host=bind, port=port)


if __name__ == "__main__":
    main()
