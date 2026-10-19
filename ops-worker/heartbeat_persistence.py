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
    normalized: Optional[Mapping[str, Any]] = None,
) -> None:
    """Upsert a host and persist its heartbeat plus the optional last event."""
    ts = to_utc(heartbeat.get("timestamp")) or now()
    summary_value = heartbeat.get("summary")
    summary = summary_value if isinstance(summary_value, Mapping) else {}
    ready = summary.get("ready")
    status_value = heartbeat.get("status")
    status = status_value if isinstance(status_value, Mapping) else {}
    operations_value = heartbeat.get("operations")
    operations = operations_value if isinstance(operations_value, Mapping) else {}

    last_forced_value = operations.get("lastForcedLogoff")
    last_forced = last_forced_value if isinstance(last_forced_value, Mapping) else {}
    last_power_value = operations.get("lastPowerAction")
    last_power = last_power_value if isinstance(last_power_value, Mapping) else {}
    station = dict(normalized or {})
    platform_value = station.get("platform")
    platform = platform_value if isinstance(platform_value, Mapping) else {}
    management_value = station.get("management")
    management = management_value if isinstance(management_value, Mapping) else {}
    local_mode = status.get("localModeEnabled", station.get("localModeEnabled"))
    sessions_value = station.get("sessions")
    sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
    local_session = status.get("localSessionActive", sessions.get("localSessionActive"))
    station_summary = station.get("summary")
    if ready is None and isinstance(station_summary, Mapping):
        ready = station_summary.get("ready")

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
                    raw_json, platform, management_transport, contract_version,
                    profile, normalized_json
                ) VALUES (
                    :host_id, :ts, :ready, :local_mode, :local_session,
                    :last_forced_ts, :last_forced_user,
                    :last_power_ts, :last_power_mode,
                    :raw_json, :platform, :management_transport, :contract_version,
                    :profile, :normalized_json
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
                "platform": platform.get("os"),
                "management_transport": management.get("transport"),
                "contract_version": station.get("contractVersion"),
                "profile": station.get("profile"),
                "normalized_json": json_dumps(station),
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
