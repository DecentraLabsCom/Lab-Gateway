#!/usr/bin/env python3
"""
Ops worker: WoL + WinRM wrapper + heartbeat poller for Lab Station hosts.
Exposes a small Flask API and optional scheduler.
"""
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from wakeonlan import send_magic_packet
import winrm
from apscheduler.schedulers.background import BackgroundScheduler

APP = Flask(__name__)

CONFIG_PATH = os.getenv("OPS_CONFIG", os.path.join(os.path.dirname(__file__), "hosts.json"))
MYSQL_DSN = os.getenv("MYSQL_DSN")
DEFAULT_LABSTATION_EXE = r"C:\LabStation\LabStation.exe"


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        logging.warning("Config file %s not found, continuing with empty host list", CONFIG_PATH)
        return {"hosts": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class HostRegistry:
    def __init__(self, cfg: Dict[str, Any]):
        self.hosts = {}
        for host in cfg.get("hosts", []):
            if "name" not in host or "address" not in host:
                continue
            key = host["name"].lower()
            self.hosts[key] = host

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.hosts.get(name.lower()) if name else None

    def all_hosts(self):
        return list(self.hosts.values())


HOSTS = HostRegistry(load_config())
DB_ENGINE: Optional[Engine] = create_engine(MYSQL_DSN, pool_pre_ping=True) if MYSQL_DSN else None


def to_utc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Handle trailing Z
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None


def wol_and_wait(mac: str, broadcast: Optional[str], port: int, ping_target: str,
                 attempts: int, wait_seconds: float) -> Tuple[bool, int]:
    send_magic_packet(mac, ip_address=broadcast or "255.255.255.255", port=port)
    for attempt in range(1, attempts + 1):
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
    session = winrm.Session(endpoint, auth=(user, password), transport=transport)
    result = session.run_cmd(exe, [command] + args)
    duration_ms = int((time.time() - start) * 1000)

    return {
        "exit_code": result.status_code,
        "stdout": (result.std_out or b"").decode("utf-8", errors="ignore"),
        "stderr": (result.std_err or b"").decode("utf-8", errors="ignore"),
        "duration_ms": duration_ms,
    }


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


def persist_heartbeat(engine: Engine, host: Dict[str, Any], heartbeat: Dict[str, Any],
                      last_event: Optional[Dict[str, Any]]) -> None:
    ts = to_utc(heartbeat.get("timestamp")) or datetime.utcnow().replace(tzinfo=timezone.utc)
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
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO reservation_operations (
                        reservation_id, lab_id, host, action, status, success,
                        response_code, duration_ms, payload, message
                    ) VALUES (
                        :reservation_id, :lab_id, :host, :action, :status, :success,
                        :response_code, :duration_ms, :payload, :message
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
                },
            )
    except Exception as exc:
        logging.error("Failed to persist reservation operation %s/%s: %s", reservation_id, action, exc)


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
    return {"heartbeat": heartbeat, "last_event": last_event}


@APP.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "hosts_loaded": len(HOSTS.all_hosts()),
        "db": bool(DB_ENGINE)
    })


@APP.route("/api/wol", methods=["POST"])
def api_wol():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    host = HOSTS.get(host_name) if host_name else None
    mac = payload.get("mac") or (host or {}).get("mac")
    if not mac:
        return jsonify({"error": "mac is required"}), 400

    ping_target = payload.get("ping_target") or (host or {}).get("ping_target") or (host or {}).get("address")
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


def _get_mandatory_field(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


@APP.route("/api/reservations/start", methods=["POST"])
def api_reservation_start():
    payload = request.get_json(force=True, silent=True) or {}
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return jsonify({"error": "reservationId and host are required"}), 400

    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404

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
    return jsonify(response), status_code


@APP.route("/api/reservations/end", methods=["POST"])
def api_reservation_end():
    payload = request.get_json(force=True, silent=True) or {}
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return jsonify({"error": "reservationId and host are required"}), 400

    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404

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
    return jsonify(response), status_code


def poll_all_hosts():
    for host in HOSTS.all_hosts():
        try:
            poll_heartbeat(host, include_events=True)
            logging.info("Polled heartbeat for %s", host.get("name"))
        except Exception as exc:
            logging.error("Heartbeat poll failed for %s: %s", host.get("name"), exc)


def start_scheduler():
    if not os.getenv("OPS_POLL_ENABLED", "false").lower() == "true":
        return
    interval = int(os.getenv("OPS_POLL_INTERVAL", "60"))
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(poll_all_hosts, "interval", seconds=interval, next_run_time=datetime.utcnow())
    scheduler.start()
    logging.info("Scheduler started (interval %ss)", interval)


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
