"""Persistence boundary for Lab Station heartbeat snapshots and events."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional


def load_persisted_heartbeat(
    engine: Any,
    lab_id: str,
    host: Mapping[str, Any],
    *,
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Load the latest raw heartbeat for the AAS synchronization boundary.

    ``lab_id`` remains part of the historical worker signature even though the
    lookup is keyed by the resolved host name.  Keeping that argument here
    makes the persistence boundary explicit without changing the route API.
    """
    if not engine:
        return None
    with engine.begin() as conn:
        heartbeat_data_row = fetch_latest_heartbeat(conn, host.get("name", ""))
        if heartbeat_data_row and heartbeat_data_row.get("raw"):
            return heartbeat_data_row["raw"]
    return None


def persist_heartbeat(
    engine: Any,
    host: Mapping[str, Any],
    heartbeat: Dict[str, Any],
    last_event: Optional[Dict[str, Any]],
    *,
    to_utc: Callable[[Any], Any],
    now: Callable[[], Any],
    sql_text: Callable[[str], Any],
    json_dumps: Callable[[Any], str],
) -> None:
    """Upsert a host and persist its heartbeat plus the optional last event."""
    ts = to_utc(heartbeat.get("timestamp")) or now()
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
            sql_text("SELECT id FROM lab_hosts WHERE name=:name"),
            {"name": host.get("name")},
        ).fetchone()
        if host_row:
            host_id = host_row[0]
            conn.execute(
                sql_text("UPDATE lab_hosts SET address=:address, mac=:mac, last_seen=:last_seen WHERE id=:id"),
                {
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                    "id": host_id,
                },
            )
        else:
            result = conn.execute(
                sql_text("INSERT INTO lab_hosts (name, address, mac, last_seen) VALUES (:name, :address, :mac, :last_seen)"),
                {
                    "name": host.get("name"),
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                },
            )
            host_id = result.lastrowid

        conn.execute(
            sql_text(
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
                "raw_json": json_dumps(heartbeat),
            },
        )

        if last_event:
            conn.execute(
                sql_text(
                    """
                    INSERT INTO lab_host_events (host_id, kind, timestamp_utc, payload)
                    VALUES (:host_id, :kind, :ts, :payload)
                    """
                ),
                {
                    "host_id": host_id,
                    "kind": "session-guard",
                    "ts": to_utc(last_event.get("timestamp")) or ts,
                    "payload": json_dumps(last_event),
                },
            )


__all__ = ["load_persisted_heartbeat", "persist_heartbeat"]
