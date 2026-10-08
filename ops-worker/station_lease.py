"""Build stable dispatcher v2 lease envelopes from durable Gateway records."""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, Optional
from uuid import NAMESPACE_URL, uuid5


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TERMINAL_RESERVATION_STATES = {"CANCELLED", "CANCELED", "COMPLETED", "ENDED", "REVOKED"}


class StationLeaseContextError(ValueError):
    """Raised when authoritative reservation data cannot authorize a lease."""


def _utc(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise StationLeaseContextError(f"{field} is unavailable") from exc
    if not isinstance(value, datetime):
        raise StationLeaseContextError(f"{field} is unavailable")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_station_dispatch_request(
    *,
    reservation_id: str,
    lab_id: str,
    host_name: str,
    command: str,
    reservation: Mapping[str, Any],
    prepare_generation: Optional[int] = None,
    release_issued_at: Optional[datetime] = None,
    start_lead_seconds: int = 120,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Create the wire metadata; callers must pass rows read from Gateway DB."""
    if command not in {"prepare-session", "release-session"}:
        raise StationLeaseContextError("station lease command is unsupported")
    if not all(_IDENTIFIER.fullmatch(str(value or "")) for value in (reservation_id, lab_id, host_name)):
        raise StationLeaseContextError("station reservation identity is invalid")
    row_lab = str(reservation.get("lab_id") or "")
    if row_lab != str(lab_id):
        raise StationLeaseContextError("reservation does not belong to the requested laboratory")
    not_before = _utc(reservation.get("start_time"), "reservation start")
    expires_at = _utc(reservation.get("end_time"), "reservation end")
    if expires_at <= not_before:
        raise StationLeaseContextError("reservation time window is invalid")
    if command == "prepare-session":
        status = str(reservation.get("status") or "").upper()
        if status not in {"CONFIRMED", "ACTIVE"}:
            raise StationLeaseContextError("reservation is not active or confirmed")
        lead = max(0, min(int(start_lead_seconds), 300))
        issued_at = not_before - timedelta(seconds=lead)
        generation = 0
    else:
        if type(prepare_generation) is not int or prepare_generation < 1:
            raise StationLeaseContextError("a successful prepare generation is unavailable")
        issued_at = release_issued_at or expires_at
        issued_at = _utc(issued_at, "release authorization time")
        generation = prepare_generation

    execute_before = issued_at + timedelta(minutes=5)
    lease_id = str(uuid5(NAMESPACE_URL, f"decentralabs:station-lease:{host_name}:{reservation_id}"))
    request_id = str(uuid5(NAMESPACE_URL, f"decentralabs:station-operation:{lease_id}:{command}:{generation}"))
    lease = {
        "kind": "reservation",
        "labId": str(lab_id),
        "reservationKey": str(reservation_id),
        "leaseId": lease_id,
        "generation": generation,
        "notBefore": _format(not_before),
        "expiresAt": _format(expires_at),
    }
    return {
        "requestId": request_id,
        "issuedAt": _format(issued_at),
        "executeBefore": _format(execute_before),
        "context": lease,
        "timeoutSeconds": timeout_seconds or (180 if command == "prepare-session" else 90),
    }


def build_demo_dispatch_request(
    *,
    demo_id: str,
    lab_id: str,
    host_name: str,
    command: str,
    issued_at: datetime,
    expires_at: datetime,
    prepare_generation: Optional[int] = None,
    release_issued_at: Optional[datetime] = None,
    start_lead_seconds: int = 120,
) -> Dict[str, Any]:
    """Build demo context from the token revocation record and durable event time."""
    if not demo_id.startswith("demo:") or not _IDENTIFIER.fullmatch(demo_id):
        raise StationLeaseContextError("demo lease identity is invalid")
    if not _IDENTIFIER.fullmatch(str(lab_id or "")) or not _IDENTIFIER.fullmatch(str(host_name or "")):
        raise StationLeaseContextError("demo host binding is invalid")
    not_before = _utc(issued_at, "demo token issue time")
    expiry = _utc(expires_at, "demo token expiry")
    if expiry <= not_before:
        raise StationLeaseContextError("demo token time window is invalid")
    if command == "prepare-session":
        lead = max(0, min(int(start_lead_seconds), 300))
        issue = not_before - timedelta(seconds=lead)
        generation = 0
    elif command == "release-session":
        if type(prepare_generation) is not int or prepare_generation < 1:
            raise StationLeaseContextError("a successful demo prepare generation is unavailable")
        issue = _utc(release_issued_at or issued_at, "demo release authorization time")
        generation = prepare_generation
    else:
        raise StationLeaseContextError("demo lease command is unsupported")
    lease = {
        "kind": "demo",
        "leaseId": demo_id,
        "generation": generation,
        "notBefore": _format(not_before),
        "expiresAt": _format(expiry),
    }
    request_id = str(uuid5(NAMESPACE_URL, f"decentralabs:station-operation:{demo_id}:{command}:{generation}"))
    return {
        "requestId": request_id,
        "issuedAt": _format(issue),
        "executeBefore": _format(issue + timedelta(minutes=5)),
        "context": lease,
        "timeoutSeconds": 180 if command == "prepare-session" else 90,
    }


def _prepared_generation(conn: Any, sql_text: Any, reservation_id: str, lab_id: str) -> int:
    row = conn.execute(
        sql_text(
            """
            SELECT payload FROM reservation_operations
            WHERE reservation_id = :reservation_id AND lab_id = :lab_id AND action = 'prepare'
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"reservation_id": reservation_id, "lab_id": lab_id},
    ).first()
    if row is None:
        raise StationLeaseContextError("no recorded prepare result is available for release")
    raw = row[0]
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        lease = payload["metadata"]["lease"]
        generation = lease["generation"]
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise StationLeaseContextError("recorded prepare result has no lease generation") from exc
    if type(generation) is not int or generation < 1:
        raise StationLeaseContextError("recorded prepare result has no lease generation")
    return generation


def resolve_station_dispatch_request(
    *,
    engine: Any,
    sql_text: Any,
    reservation_id: str,
    lab_id: str,
    host_name: str,
    command: str,
    start_lead_seconds: int = 120,
) -> Dict[str, Any]:
    """Resolve a v2 envelope from reservation/token rows and recorded prepare."""
    if not engine:
        raise StationLeaseContextError("Gateway reservation database is unavailable")
    try:
        with engine.connect() as conn:
            if reservation_id.startswith("demo:"):
                jti = reservation_id.removeprefix("demo:")
                if not jti:
                    raise StationLeaseContextError("demo token identity is invalid")
                token = conn.execute(
                    sql_text(
                        """
                        SELECT expires_at, created_at FROM guacamole_token_revocation_queue
                        WHERE jwt_jti = :jti ORDER BY created_at DESC LIMIT 1
                        """
                    ),
                    {"jti": jti},
                ).first()
                if token is None:
                    raise StationLeaseContextError("demo token expiry is not recorded in Gateway")
                generation = _prepared_generation(conn, sql_text, reservation_id, lab_id) if command == "release-session" else None
                release_issue = None
                if command == "release-session":
                    event = conn.execute(
                        sql_text(
                            """
                            SELECT created_at FROM reservation_operations
                            WHERE reservation_id = :reservation_id AND lab_id = :lab_id
                              AND action IN ('demo_expiry', 'demo_failure', 'demo_disconnect')
                            ORDER BY id DESC LIMIT 1
                            """
                        ),
                        {"reservation_id": reservation_id, "lab_id": lab_id},
                    ).first()
                    if event is None:
                        raise StationLeaseContextError("demo release event is not recorded")
                    release_issue = event[0]
                return build_demo_dispatch_request(
                    demo_id=reservation_id,
                    lab_id=lab_id,
                    host_name=host_name,
                    command=command,
                    issued_at=token[1],
                    expires_at=token[0],
                    prepare_generation=generation,
                    release_issued_at=release_issue,
                    start_lead_seconds=start_lead_seconds,
                )

            row = conn.execute(
                sql_text(
                    """
                    SELECT lab_id, start_time, end_time, status, updated_at
                    FROM lab_reservations WHERE transaction_hash = :reservation_id LIMIT 1
                    """
                ),
                {"reservation_id": reservation_id},
            ).mappings().first()
            if row is None:
                raise StationLeaseContextError("reservation does not exist in Gateway records")
            generation = _prepared_generation(conn, sql_text, reservation_id, lab_id) if command == "release-session" else None
            state = str(row.get("status") or "").upper()
            release_issued_at = row.get("updated_at") if command == "release-session" and state in _TERMINAL_RESERVATION_STATES else None
            return build_station_dispatch_request(
                reservation_id=reservation_id,
                lab_id=lab_id,
                host_name=host_name,
                command=command,
                reservation=row,
                prepare_generation=generation,
                release_issued_at=release_issued_at,
                start_lead_seconds=start_lead_seconds,
            )
    except StationLeaseContextError:
        raise
    except Exception as exc:
        raise StationLeaseContextError("authoritative station lease data could not be read") from exc


__all__ = [
    "StationLeaseContextError",
    "build_demo_dispatch_request",
    "build_station_dispatch_request",
    "resolve_station_dispatch_request",
]
