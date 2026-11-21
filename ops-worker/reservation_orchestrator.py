"""Reservation automation orchestration with explicit runtime dependencies."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
import json
from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import uuid4

from sqlalchemy.engine import Connection


class SchedulerProtocol(Protocol):
    """Minimal scheduler surface required by the reservation orchestrator."""

    def add_job(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class ReservationOrchestrator:
    def __init__(
        self,
        engine: Optional[Any],
        registry: Any,
        *,
        parse_bool: Callable[..., bool],
        get_env: Callable[..., Any],
        env_or_secret_file: Callable[[str], str],
        parse_reservation_datetime: Callable[[Any], Optional[datetime]],
        as_utc_datetime: Callable[[Any], Optional[datetime]],
        http_get: Callable[..., Any],
        sql_text: Callable[[str], Any],
        bindparam: Callable[..., Any],
        dispatch_start: Callable[..., Any],
        dispatch_end: Callable[..., Any],
        resolve_host_by_lab: Callable[[str], Optional[Mapping[str, Any]]],
        record_operation: Callable[..., Any],
        logger: Any,
        now: Callable[[], datetime],
        read_station_status: Callable[..., Any] = lambda host: {},
    ):
        self.engine = engine
        self.registry = registry
        self.parse_reservation_datetime = parse_reservation_datetime
        self.as_utc_datetime = as_utc_datetime
        self.http_get = http_get
        self.sql_text = sql_text
        self.bindparam = bindparam
        self.dispatch_start = dispatch_start
        self.dispatch_end = dispatch_end
        self.resolve_host_by_lab = resolve_host_by_lab
        self.record_operation = record_operation
        self.logger = logger
        self.now = now
        self.read_station_status = read_station_status
        self.get_env = get_env
        self.enabled = parse_bool(get_env("OPS_RESERVATION_AUTOMATION", False), False)
        self.scan_interval = int(get_env("OPS_RESERVATION_SCAN_INTERVAL", "10"))
        self.start_lead = int(get_env("OPS_RESERVATION_START_LEAD", "120"))
        self.lookback = int(get_env("OPS_RESERVATION_LOOKBACK", "21600"))
        self.retry_cooldown = int(get_env("OPS_RESERVATION_RETRY_COOLDOWN", "60"))
        try:
            self.disconnect_grace = max(
                1,
                min(300, int(get_env("OPS_RESERVATION_DISCONNECT_GRACE_SECONDS", "120"))),
            )
        except (TypeError, ValueError):
            self.disconnect_grace = 120
        try:
            self.disconnect_close_fallback = max(
                self.disconnect_grace,
                min(3600, int(get_env("OPS_RESERVATION_DISCONNECT_CLOSE_FALLBACK_SECONDS", "180"))),
            )
        except (TypeError, ValueError):
            self.disconnect_close_fallback = max(self.disconnect_grace, 180)
        self.projection_url = str(get_env("RESERVATION_PROJECTION_URL", "") or "").strip().rstrip("/")
        self.projection_gateway_id = str(get_env("RESERVATION_PROJECTION_GATEWAY_ID", "") or "").strip().lower()
        self.projection_token = env_or_secret_file("RESERVATION_PROJECTION_TOKEN")
        if self.projection_url and not (self.projection_gateway_id and self.projection_token):
            self.logger.error(
                "Reservation projection is configured but gateway ID or token is missing; "
                "remote reservation automation will remain unavailable"
            )

    def register(self, scheduler: SchedulerProtocol) -> int:
        if not self.enabled:
            self.logger.info("Reservation orchestrator disabled (OPS_RESERVATION_AUTOMATION=false)")
            return 0
        if not self.engine:
            self.logger.warning("Reservation orchestrator disabled: ops database DSN is not configured")
            return 0
        scheduler.add_job(
            self.scan_once,
            "interval",
            seconds=self.scan_interval,
            next_run_time=self.now(),
            id="reservation-orchestrator",
            replace_existing=True,
        )
        self.logger.info(
            "Reservation orchestrator enabled (scan=%ss, lead=%ss, end dispatch at scheduled end)",
            self.scan_interval,
            self.start_lead,
        )
        return 1

    def scan_once(self):
        if not self.enabled or not self.engine:
            return
        now = self.now()
        try:
            with self.engine.begin() as conn:
                if self.projection_url:
                    remote_rows = self._fetch_remote_candidates(now)
                    start_rows, end_rows = self._select_remote_candidates(conn, remote_rows, now)
                else:
                    remote_rows = []
                    start_rows = self._fetch_start_candidates(conn, now)
                    end_rows = self._fetch_end_candidates(conn, now)
                lifecycle_rows = self._fetch_connection_lifecycle_candidates(
                    conn,
                    now,
                    remote_rows=remote_rows,
                )
        except Exception as exc:
            self.logger.error("Reservation orchestrator query failed: %s", exc)
            return

        for row in start_rows:
            self._dispatch_start(dict(row))
        scheduled_end_ids = {str(row.get("transaction_hash") or "") for row in end_rows}
        for row in lifecycle_rows:
            reservation_id = str(row.get("transaction_hash") or "")
            if (
                row.get("_lifecycle_state") == "RESUMING"
                and reservation_id not in scheduled_end_ids
                and reservation_id not in {str(item.get("transaction_hash") or "") for item in start_rows}
            ):
                self._dispatch_resume(dict(row))

        end_by_id = {str(row.get("transaction_hash") or ""): row for row in end_rows}
        for row in lifecycle_rows:
            reservation_id = str(row.get("transaction_hash") or "")
            if row.get("_lifecycle_state") == "ENDING":
                end_by_id[reservation_id] = row
            elif row.get("_lifecycle_state") == "CLOSING":
                station_close_at: Optional[datetime] = None
                station_status: Optional[Mapping[str, Any]] = None
                used_close_fallback = False
                if row.get("_requires_station_close"):
                    station_status = self._read_station_status(row)
                    station_close_at = self._station_disconnect_close_completed(row, station_status)
                    if station_close_at is None:
                        if not self._disconnect_close_fallback_due(row):
                            continue
                        station_close_at = self._station_disconnect_close_fallback_at(row, station_status)
                        if station_close_at is None:
                            continue
                        used_close_fallback = True
                        self.logger.warning(
                            "Reservation disconnect close result missing after %ss; using verified fallback "
                            "reservation=%s",
                            self.disconnect_close_fallback,
                            reservation_id,
                        )
                if not self._claim_connection_lifecycle_end(
                    row,
                    station_close_at=station_close_at,
                    require_no_active_connections=used_close_fallback,
                ):
                    resume_cycle_id = self._claim_connection_lifecycle_resume(
                        row,
                        station_close_at=station_close_at,
                    )
                    if resume_cycle_id:
                        resume_row = dict(row)
                        resume_row["_lifecycle_state"] = "RESUMING"
                        resume_row["_lifecycle_cycle_id"] = resume_cycle_id
                        resume_row["_lifecycle_updated_at"] = self.now().replace(tzinfo=None)
                        self._dispatch_resume(resume_row)
                    continue
                ending_row = dict(row)
                ending_row["_lifecycle_state"] = "ENDING"
                ending_row["_lifecycle_updated_at"] = self.now().replace(tzinfo=None)
                end_by_id[reservation_id] = ending_row
        for row in end_by_id.values():
            self._dispatch_end(dict(row))

    def _fetch_connection_lifecycle_candidates(
        self,
        conn: Connection,
        now: datetime,
        *,
        remote_rows: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Claim due disconnects and load pending resume/end work."""
        max_batch = min(500, max(1, int(self.get_env("OPS_RESERVATION_MAX_BATCH", "200"))))
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        grace_deadline = now - timedelta(seconds=self.disconnect_grace)
        query = self.sql_text(
            """
            SELECT reservation_id, lab_id, state, disconnected_at, cycle_id, updated_at,
                   EXISTS (
                       SELECT 1 FROM reservation_session_connections c
                       WHERE c.reservation_id=l.reservation_id AND c.source='guacamole'
                   ) AS has_guacamole_connection,
                   (
                       SELECT MAX(c.disconnected_at) FROM reservation_session_connections c
                       WHERE c.reservation_id=l.reservation_id AND c.state='DISCONNECTED'
                   ) AS last_connection_disconnected_at
            FROM reservation_session_lifecycle l
            WHERE (
                (l.state='GRACE' AND l.disconnected_at <= :grace_deadline)
                OR l.state='CLOSING'
                OR l.state='ENDING'
                OR l.state='RESUMING'
            )
            ORDER BY COALESCE(l.disconnected_at, l.updated_at) ASC
            LIMIT :max_batch
            """
        )
        lifecycle_rows = [dict(row) for row in conn.execute(
            query,
            {
                "grace_deadline": grace_deadline,
                "max_batch": max_batch,
            },
        ).mappings()]
        if not lifecycle_rows:
            return []

        reservation_ids = [str(row["reservation_id"]) for row in lifecycle_rows]
        if self.projection_url:
            reservations_by_id = {
                str(row.get("transaction_hash") or ""): dict(row)
                for row in remote_rows
                if str(row.get("transaction_hash") or "") in reservation_ids
            }
        else:
            reservations_by_id = {}
            result = conn.execute(
                self.sql_text(
                    """
                    SELECT transaction_hash, lab_id, start_time, end_time, status
                    FROM lab_reservations
                    WHERE transaction_hash IN :reservation_ids
                      AND status IN ('CONFIRMED', 'ACTIVE')
                    """
                ).bindparams(self.bindparam("reservation_ids", expanding=True)),
                {"reservation_ids": reservation_ids},
            )
            reservations_by_id = {
                str(row.get("transaction_hash") or ""): dict(row)
                for row in result.mappings()
            }

        candidates: List[Dict[str, Any]] = []
        for lifecycle in lifecycle_rows:
            reservation_id = str(lifecycle.get("reservation_id") or "")
            reservation = reservations_by_id.get(reservation_id)
            if not reservation:
                continue
            if str(reservation.get("lab_id") or "") != str(lifecycle.get("lab_id") or ""):
                self.logger.error("Reservation session lab binding mismatch for %s", reservation_id)
                continue
            state = str(lifecycle.get("state") or "").upper()
            end_time = self.as_utc_datetime(reservation.get("end_time"))
            if end_time is None or end_time <= now:
                # The scheduled end path owns the final reservation boundary.
                continue
            if state == "GRACE":
                result = conn.execute(
                    self.sql_text(
                        """
                        UPDATE reservation_session_lifecycle
                        SET state='CLOSING', updated_at=:now
                        WHERE reservation_id=:reservation_id
                          AND state='GRACE' AND disconnected_at <= :grace_deadline
                        """
                    ),
                    {
                        "reservation_id": reservation_id,
                        "now": now.replace(tzinfo=None),
                        "grace_deadline": grace_deadline,
                    },
                )
                if not result.rowcount:
                    continue
                state = "CLOSING"
                lifecycle["updated_at"] = now.replace(tzinfo=None)
            reservation["_lifecycle_state"] = state
            reservation["_lifecycle_cycle_id"] = lifecycle.get("cycle_id")
            reservation["_lifecycle_updated_at"] = lifecycle.get("updated_at")
            reservation["_lifecycle_disconnected_at"] = lifecycle.get("disconnected_at")
            reservation["_lifecycle_last_connection_disconnected_at"] = lifecycle.get("last_connection_disconnected_at")
            reservation["_requires_station_close"] = bool(lifecycle.get("has_guacamole_connection"))
            candidates.append(reservation)

        if not candidates:
            return []

        candidate_ids = [str(row.get("transaction_hash") or "") for row in candidates]
        recent = conn.execute(
            self.sql_text(
                """
                SELECT reservation_id, action, success
                FROM reservation_operations
                WHERE reservation_id IN :reservation_ids AND created_at >= :retry_cutoff
                """
            ).bindparams(self.bindparam("reservation_ids", expanding=True)),
            {"reservation_ids": candidate_ids, "retry_cutoff": retry_cutoff},
        ).mappings()
        recent_by_reservation: Dict[str, Dict[str, bool]] = {}
        for operation in recent:
            recent_by_reservation.setdefault(str(operation.get("reservation_id") or ""), {})[
                str(operation.get("action") or "")
            ] = bool(operation.get("success"))

        retryable_candidates = []
        for row in candidates:
            reservation_id = str(row.get("transaction_hash") or "")
            cycle_id = str(row.get("_lifecycle_cycle_id") or "")
            state = str(row.get("_lifecycle_state") or "").upper()
            action = (
                f"scheduler:disconnect-end:{cycle_id}"
                if state in {"CLOSING", "ENDING"}
                else f"scheduler:r:{cycle_id}"
            )
            if not cycle_id:
                self.logger.error("Reservation connection lifecycle has no cycle identity for %s", reservation_id)
                continue
            if recent_by_reservation.get(reservation_id, {}).get(action) is False:
                continue
            retryable_candidates.append(row)
        return retryable_candidates

    def _read_station_status(self, row: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        reservation_id = str(row.get("transaction_hash") or "").strip()
        lab_id = str(row.get("lab_id") or "").strip()
        host = self.resolve_host_by_lab(lab_id) if lab_id else None
        if not reservation_id or not lab_id or not host:
            return None
        try:
            result = self.read_station_status(host)
            if result is None:
                return None
            if not isinstance(result, Mapping):
                return None
            exit_code = result.get("exitCode", result.get("exit_code", 2))
            if int(exit_code) >= 2:
                return None
            payload = json.loads(str(result.get("stdout") or "").lstrip("\ufeff"))
        except Exception as exc:
            self.logger.warning("Unable to read Station close status for reservation %s: %s", reservation_id, exc)
            return None
        if not isinstance(payload, Mapping):
            return None
        status = payload.get("status") if isinstance(payload.get("status"), Mapping) else payload
        return status if isinstance(status, Mapping) else None

    def _station_disconnect_close_completed(
        self,
        row: Mapping[str, Any],
        status: Optional[Mapping[str, Any]],
    ) -> Optional[datetime]:
        if status is None:
            return None
        if not isinstance(status, Mapping):
            return None
        reservation_id = str(row.get("transaction_hash") or "").strip()
        lab_id = str(row.get("lab_id") or "").strip()
        observed_at = self.as_utc_datetime(status.get("timestamp"))
        if str(status.get("profile") or "").strip().lower() == "fmu-only":
            return observed_at or self.now()
        close = status.get("reservationDisconnectClose")
        if isinstance(close, Mapping) and (
            close.get("reservationKey") == reservation_id
            and close.get("labId") == lab_id
            and str(close.get("leaseId") or "").strip()
            and type(close.get("generation")) is int
            and close.get("generation", 0) >= 1
            and close.get("success") is True
            and close.get("method") in {"app-control", "station-controlled", "session-ended"}
        ):
            completed_at = self.as_utc_datetime(close.get("completedAt"))
            disconnected_at = self.as_utc_datetime(row.get("_lifecycle_disconnected_at"))
            if completed_at is not None:
                completion_is_observed = observed_at is None or completed_at <= observed_at + timedelta(seconds=5)
                belongs_to_disconnect = disconnected_at is None or completed_at >= disconnected_at
                if completion_is_observed and belongs_to_disconnect:
                    return completed_at

        sessions = status.get("sessions")
        if isinstance(sessions, Mapping):
            remote_ids = sessions.get("remoteLabUserSessionIds")
            disconnected_at = self.as_utc_datetime(row.get("_lifecycle_disconnected_at"))
            after_disconnect = disconnected_at is None or (observed_at is not None and observed_at >= disconnected_at)
            if (
                sessions.get("queryOk") is True
                and isinstance(remote_ids, list)
                and not remote_ids
                and observed_at is not None
                and after_disconnect
            ):
                return observed_at
        return None

    def _disconnect_close_fallback_due(self, row: Mapping[str, Any]) -> bool:
        disconnect_at = self._latest_disconnect_at(row)
        now = self.as_utc_datetime(self.now())
        if disconnect_at is None or now is None:
            return False
        fallback_at = disconnect_at + timedelta(seconds=self.disconnect_close_fallback)
        if now < fallback_at:
            return False
        end_time = self.as_utc_datetime(row.get("end_time"))
        if end_time is not None:
            # Let the scheduled end own cleanup when it is within the Station
            # disconnect grace. Avoid ending energy/session phases early just
            # because the disconnect fallback became due first.
            if end_time <= now or fallback_at > end_time - timedelta(seconds=self.disconnect_grace):
                return False
        return True

    def _latest_disconnect_at(self, row: Mapping[str, Any]) -> Optional[datetime]:
        disconnect_at = self.as_utc_datetime(row.get("_lifecycle_disconnected_at"))
        latest_connection_disconnect = self.as_utc_datetime(
            row.get("_lifecycle_last_connection_disconnected_at")
        )
        if latest_connection_disconnect is not None and (
            disconnect_at is None or latest_connection_disconnect > disconnect_at
        ):
            return latest_connection_disconnect
        return disconnect_at

    def _station_disconnect_close_fallback_at(
        self,
        row: Mapping[str, Any],
        status: Optional[Mapping[str, Any]],
    ) -> Optional[datetime]:
        if status is None:
            return None
        if not isinstance(status, Mapping):
            return None
        observed_at = self.as_utc_datetime(status.get("timestamp"))
        now = self.as_utc_datetime(self.now())
        sessions = status.get("sessions")
        if observed_at is None or now is None or not isinstance(sessions, Mapping):
            return None
        if observed_at > now + timedelta(seconds=5) or now - observed_at > timedelta(seconds=30):
            return None
        disconnect_at = self._latest_disconnect_at(row)
        if disconnect_at is not None and observed_at < disconnect_at:
            return None
        if (
            sessions.get("queryOk") is not True
            or sessions.get("remoteClientStateKnown") is not True
            or sessions.get("remoteClientConnected") is not False
            or sessions.get("localSessionActive") is not False
            or status.get("localModeEnabled") is not False
        ):
            return None
        return observed_at

    def _claim_connection_lifecycle_end(
        self,
        row: Mapping[str, Any],
        *,
        station_close_at: Optional[datetime] = None,
        require_no_active_connections: bool = False,
    ) -> bool:
        reservation_id = str(row.get("transaction_hash") or "")
        lab_id = str(row.get("lab_id") or "")
        cycle_id = str(row.get("_lifecycle_cycle_id") or "")
        if not reservation_id or not lab_id or not cycle_id or not self.engine:
            return False
        if row.get("_requires_station_close") and station_close_at is None:
            return False
        close_completed_at = station_close_at.replace(tzinfo=None) if station_close_at is not None else None
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    self.sql_text(
                        "UPDATE reservation_session_lifecycle "
                        "SET state='ENDING', updated_at=:now "
                        "WHERE reservation_id=:reservation_id AND lab_id=:lab_id "
                        "AND state='CLOSING' AND cycle_id=:cycle_id "
                        "AND (:station_close_at IS NULL OR NOT EXISTS ("
                        "SELECT 1 FROM reservation_session_connections c "
                        "WHERE c.reservation_id=:reservation_id AND c.source='guacamole' "
                        "AND c.connected_at > :station_close_at)) "
                        "AND (:require_no_active_connections=0 OR NOT EXISTS ("
                        "SELECT 1 FROM reservation_session_connections a "
                        "WHERE a.reservation_id=:reservation_id AND a.state='CONNECTED'))"
                    ),
                    {
                        "reservation_id": reservation_id,
                        "lab_id": lab_id,
                        "cycle_id": cycle_id,
                        "now": self.now().replace(tzinfo=None),
                        "station_close_at": close_completed_at,
                        "require_no_active_connections": int(require_no_active_connections),
                    },
                )
                return bool(result.rowcount)
        except Exception as exc:
            self.logger.warning("Unable to claim reservation end after Station close for %s: %s", reservation_id, exc)
            return False

    def _claim_connection_lifecycle_resume(
        self,
        row: Mapping[str, Any],
        *,
        station_close_at: Optional[datetime],
    ) -> Optional[str]:
        """Resume a late reconnect after Station closed apps but before end dispatch began."""
        reservation_id = str(row.get("transaction_hash") or "")
        lab_id = str(row.get("lab_id") or "")
        disconnect_cycle_id = str(row.get("_lifecycle_cycle_id") or "")
        if not reservation_id or not lab_id or not disconnect_cycle_id or not station_close_at or not self.engine:
            return None

        close_completed_at = station_close_at.replace(tzinfo=None)
        try:
            with self.engine.begin() as conn:
                pending = conn.execute(
                    self.sql_text(
                        "SELECT cycle_id FROM reservation_session_connections "
                        "WHERE reservation_id=:reservation_id AND lab_id=:lab_id "
                        "AND source='guacamole' AND state='CONNECTED' "
                        "AND cycle_id IS NOT NULL AND connected_at > :station_close_at "
                        "ORDER BY connected_at DESC LIMIT 1"
                    ),
                    {
                        "reservation_id": reservation_id,
                        "lab_id": lab_id,
                        "station_close_at": close_completed_at,
                    },
                ).scalar_one_or_none()
                resume_cycle_id = str(pending or "").strip()
                if not resume_cycle_id:
                    return None

                result = conn.execute(
                    self.sql_text(
                        "UPDATE reservation_session_lifecycle "
                        "SET state='RESUMING', disconnected_at=NULL, cycle_id=:resume_cycle_id, updated_at=:now "
                        "WHERE reservation_id=:reservation_id AND lab_id=:lab_id "
                        "AND state='CLOSING' AND cycle_id=:disconnect_cycle_id "
                        "AND EXISTS ("
                        "SELECT 1 FROM reservation_session_connections c "
                        "WHERE c.reservation_id=:reservation_id AND c.lab_id=:lab_id "
                        "AND c.source='guacamole' AND c.state='CONNECTED' "
                        "AND c.cycle_id=:resume_cycle_id AND c.connected_at > :station_close_at)"
                    ),
                    {
                        "reservation_id": reservation_id,
                        "lab_id": lab_id,
                        "disconnect_cycle_id": disconnect_cycle_id,
                        "resume_cycle_id": resume_cycle_id,
                        "station_close_at": close_completed_at,
                        "now": self.now().replace(tzinfo=None),
                    },
                )
                return resume_cycle_id if result.rowcount else None
        except Exception as exc:
            self.logger.warning("Unable to claim reservation resume after Station close for %s: %s", reservation_id, exc)
            return None

    def _fetch_remote_candidates(self, now: datetime, *, strict: bool = False) -> List[Dict[str, Any]]:
        if not self.projection_gateway_id or not self.projection_token:
            raise RuntimeError("Reservation projection credentials are not configured")
        window_lower = now - timedelta(seconds=self.lookback)
        window_upper = now + timedelta(seconds=self.start_lead)
        max_batch = min(500, max(1, int(self.get_env("OPS_RESERVATION_MAX_BATCH", "200"))))
        response = self.http_get(
            self.projection_url,
            headers={
                "X-Gateway-ID": self.projection_gateway_id,
                "X-Reservation-Projection-Token": self.projection_token,
            },
            params={
                "from": window_lower.isoformat().replace("+00:00", "Z"),
                "to": window_upper.isoformat().replace("+00:00", "Z"),
                "limit": max_batch,
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Reservation projection returned HTTP {response.status_code}")
        body = response.json()
        if not isinstance(body, dict) or str(body.get("gatewayId", "")).strip().lower() != self.projection_gateway_id:
            raise RuntimeError("Reservation projection response is not scoped to this gateway")
        reservations = body.get("reservations")
        if not isinstance(reservations, list):
            raise RuntimeError("Reservation projection response has an invalid reservations field")
        if strict and len(reservations) >= max_batch:
            raise RuntimeError("Reservation projection may be truncated; reservation state is not complete")

        rows: List[Dict[str, Any]] = []
        for item in reservations:
            if not isinstance(item, dict):
                if strict:
                    raise RuntimeError("Reservation projection contains a malformed reservation")
                continue
            transaction_hash = str(item.get("transactionHash") or item.get("transaction_hash") or "").strip()
            lab_id = str(item.get("labId") or item.get("lab_id") or "").strip()
            status = str(item.get("status") or "").strip().upper()
            start_time = self.parse_reservation_datetime(item.get("startTime") or item.get("start_time"))
            end_time = self.parse_reservation_datetime(item.get("endTime") or item.get("end_time"))
            if status not in {"CONFIRMED", "ACTIVE"}:
                continue
            if not transaction_hash or not lab_id:
                if strict:
                    raise RuntimeError("Active reservation projection is missing its identity or lab")
                continue
            if start_time is None or end_time is None:
                if strict:
                    raise RuntimeError("Active reservation projection has invalid time bounds")
                self.logger.warning("Ignoring remote reservation %s with invalid time window", transaction_hash)
                continue
            rows.append({
                "transaction_hash": transaction_hash,
                "lab_id": lab_id,
                "start_time": start_time,
                "end_time": end_time,
                "status": status,
            })
        return rows

    def _select_remote_candidates(
        self,
        conn: Connection,
        rows: Sequence[Mapping[str, Any]],
        now: datetime,
    ) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
        if not rows:
            return [], []
        reservation_ids = [str(row.get("transaction_hash")) for row in rows if row.get("transaction_hash")]
        successful_actions = set()
        recent_actions = set()
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        operation_query = self.sql_text(
            """
            SELECT reservation_id, action, success, created_at
            FROM reservation_operations
            WHERE reservation_id IN :reservation_ids
              AND action IN ('scheduler:start', 'scheduler:end')
              AND (success = 1 OR created_at >= :retry_cutoff)
            """
        ).bindparams(self.bindparam("reservation_ids", expanding=True))
        result = conn.execute(
            operation_query,
            {"reservation_ids": reservation_ids, "retry_cutoff": retry_cutoff},
        )
        for operation in result.mappings():
            key = (str(operation["reservation_id"]), str(operation["action"]))
            if bool(operation["success"]):
                successful_actions.add(key)
            else:
                recent_actions.add(key)

        window_upper = now + timedelta(seconds=self.start_lead)
        window_lower = now - timedelta(seconds=self.lookback)
        ready_time = now
        start_rows: List[Mapping[str, Any]] = []
        end_rows: List[Mapping[str, Any]] = []
        for row in rows:
            reservation_id = str(row.get("transaction_hash"))
            status = str(row.get("status") or "").upper()
            start_time = self.as_utc_datetime(row.get("start_time"))
            end_time = self.as_utc_datetime(row.get("end_time"))
            if (
                status == "CONFIRMED"
                and start_time is not None
                and window_lower <= start_time <= window_upper
                and (reservation_id, "scheduler:start") not in successful_actions
                and (reservation_id, "scheduler:start") not in recent_actions
            ):
                start_rows.append(row)
            if (
                status in {"CONFIRMED", "ACTIVE"}
                and end_time is not None
                and window_lower <= end_time <= ready_time
                and (reservation_id, "scheduler:end") not in successful_actions
                and (reservation_id, "scheduler:end") not in recent_actions
            ):
                end_rows.append(row)
        return start_rows, end_rows

    def _fetch_start_candidates(self, conn: Connection, now: datetime):
        if conn.dialect.name == "mysql":
            conn.execute(self.sql_text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        window_upper = now + timedelta(seconds=self.start_lead)
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(self.get_env("OPS_RESERVATION_MAX_BATCH", "200"))
        query = self.sql_text(
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
            conn.execute(self.sql_text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        ready_time = now
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(self.get_env("OPS_RESERVATION_MAX_BATCH", "200"))
        query = self.sql_text(
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
        lab_id = str(row.get("lab_id") or "").strip()
        host = self.resolve_host_by_lab(lab_id) if lab_id else None
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            self.logger.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "start", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
            # Each scheduler retry needs a fresh Station dispatcher window and
            # idempotency key; a reservation-start-derived window expires while
            # the reservation itself may still be active.
            "prepareAttempt": uuid4().hex,
        }
        dispatch_kwargs: Dict[str, Any] = {}
        if self.projection_url:
            dispatch_kwargs["authoritative_reservation"] = dict(row)
        response, status_code = self.dispatch_start(payload, **dispatch_kwargs)
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

    def _dispatch_resume(self, row: Mapping[str, Any]):
        reservation_id = str(row.get("transaction_hash") or "")
        lab_id = str(row.get("lab_id") or "").strip()
        cycle_id = str(row.get("_lifecycle_cycle_id") or "").strip()
        if not reservation_id or not cycle_id:
            self.logger.error("Reservation reconnect lifecycle has no operation identity")
            return
        action_suffix = f"r:{cycle_id}"
        action = f"scheduler:{action_suffix}"
        if self._lifecycle_action_succeeded(reservation_id, action):
            self._mark_connection_lifecycle(reservation_id, lab_id, "ACTIVE", cycle_id=cycle_id)
            return

        host = self.resolve_host_by_lab(lab_id) if lab_id else None
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            self.logger.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, action_suffix, False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
            "wake": False,
            "prepareAttempt": cycle_id,
            "powerExecutionId": cycle_id,
            "actor": "reservation-reconnect",
        }
        prepare_issued_at = self.as_utc_datetime(row.get("_lifecycle_updated_at"))
        if prepare_issued_at is not None:
            payload["prepareIssuedAt"] = prepare_issued_at.isoformat()
        dispatch_kwargs: Dict[str, Any] = {}
        if self.projection_url:
            dispatch_kwargs["authoritative_reservation"] = dict(row)
        response, status_code = self.dispatch_start(payload, **dispatch_kwargs)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation reconnect preparation failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            action_suffix,
            success,
            message,
            payload={"response": response, "status_code": status_code, "cycleId": cycle_id},
            response_code=status_code,
        )
        if success:
            self._mark_connection_lifecycle(reservation_id, lab_id, "ACTIVE", cycle_id=cycle_id)

    def _dispatch_end(self, row: Mapping[str, Any]):
        reservation_id = row["transaction_hash"]
        lab_id = str(row.get("lab_id") or "").strip()
        lifecycle_end = str(row.get("_lifecycle_state") or "").upper() == "ENDING"
        end_time = self.as_utc_datetime(row.get("end_time"))
        disconnect_end = lifecycle_end and end_time is not None and end_time > self.now()
        cycle_id = str(row.get("_lifecycle_cycle_id") or "").strip()
        action_suffix = f"disconnect-end:{cycle_id}" if disconnect_end else "end"
        action = f"scheduler:{action_suffix}"
        if disconnect_end and self._lifecycle_action_succeeded(reservation_id, action):
            self._mark_connection_lifecycle(reservation_id, lab_id, "RELEASED")
            return
        host = self.resolve_host_by_lab(lab_id) if lab_id else None
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            self.logger.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, action_suffix, False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        if disconnect_end:
            payload["releaseAttempt"] = cycle_id
            payload["powerExecutionId"] = cycle_id
            payload["actor"] = "reservation-disconnect"
            release_issued_at = self.as_utc_datetime(row.get("_lifecycle_updated_at"))
            if release_issued_at is not None:
                payload["releaseIssuedAt"] = release_issued_at.isoformat()
        dispatch_kwargs: Dict[str, Any] = {}
        if self.projection_url:
            dispatch_kwargs["authoritative_reservation"] = dict(row)
        previous_release_succeeded = self._last_end_release_succeeded(reservation_id, action)
        if previous_release_succeeded is not None:
            dispatch_kwargs["reconciliation_attempt"] = uuid4().hex
            dispatch_kwargs["reconciliation_only"] = not previous_release_succeeded
        response, status_code = self.dispatch_end(payload, **dispatch_kwargs)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation end failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            action_suffix,
            success,
            message,
            payload={"response": response, "status_code": status_code},
            response_code=status_code,
        )
        if success:
            if disconnect_end:
                self._mark_connection_lifecycle(reservation_id, lab_id, "RELEASED")
            else:
                self._update_status(reservation_id, row.get("status"), "COMPLETED")
                self._mark_connection_lifecycle(reservation_id, lab_id, "ENDED")

    def _lifecycle_action_succeeded(self, reservation_id: str, action: str) -> bool:
        if not self.engine:
            return False
        try:
            with self.engine.connect() as conn:
                return conn.execute(
                    self.sql_text(
                        "SELECT 1 FROM reservation_operations "
                        "WHERE reservation_id=:reservation_id AND action=:action AND success=1 "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"reservation_id": reservation_id, "action": action},
                ).first() is not None
        except Exception as exc:
            self.logger.warning(
                "Unable to inspect prior reconnect operation for %s: %s",
                reservation_id,
                exc,
            )
            return False

    def _mark_connection_lifecycle(
        self,
        reservation_id: str,
        lab_id: str,
        state: str,
        *,
        cycle_id: Optional[str] = None,
    ) -> None:
        if not self.engine:
            return
        try:
            with self.engine.begin() as conn:
                if state == "ACTIVE":
                    now = self.now().replace(tzinfo=None)
                    active_count = conn.execute(
                        self.sql_text(
                            "SELECT COUNT(*) FROM reservation_session_connections "
                            "WHERE reservation_id=:reservation_id AND state='CONNECTED'"
                        ),
                        {"reservation_id": reservation_id},
                    ).scalar_one()
                    if active_count:
                        conn.execute(
                            self.sql_text(
                                """
                                UPDATE reservation_session_lifecycle
                                SET state='ACTIVE', disconnected_at=NULL, cycle_id=NULL, updated_at=:now
                                WHERE reservation_id=:reservation_id AND state='RESUMING' AND cycle_id=:cycle_id
                                """
                            ),
                            {"reservation_id": reservation_id, "cycle_id": cycle_id, "now": now},
                        )
                    else:
                        conn.execute(
                            self.sql_text(
                                """
                                UPDATE reservation_session_lifecycle
                                SET state='GRACE', disconnected_at=:now, cycle_id=:next_cycle_id, updated_at=:now
                                WHERE reservation_id=:reservation_id AND state='RESUMING' AND cycle_id=:cycle_id
                                """
                            ),
                            {
                                "reservation_id": reservation_id,
                                "cycle_id": cycle_id,
                                "next_cycle_id": uuid4().hex[:24],
                                "now": now,
                            },
                        )
                    return

                now = self.now().replace(tzinfo=None)
                if state == "RELEASED":
                    pending_resume = conn.execute(
                        self.sql_text(
                            "SELECT cycle_id FROM reservation_session_connections "
                            "WHERE reservation_id=:reservation_id AND state='CONNECTED' "
                            "AND cycle_id IS NOT NULL ORDER BY connected_at ASC LIMIT 1"
                        ),
                        {"reservation_id": reservation_id},
                    ).scalar_one_or_none()
                    if pending_resume:
                        conn.execute(
                            self.sql_text(
                                """
                                UPDATE reservation_session_lifecycle
                                SET state='RESUMING', disconnected_at=NULL, cycle_id=:cycle_id, updated_at=:now
                                WHERE reservation_id=:reservation_id AND state='ENDING'
                                """
                            ),
                            {
                                "reservation_id": reservation_id,
                                "cycle_id": pending_resume,
                                "now": now,
                            },
                        )
                        return
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE reservation_session_lifecycle
                            SET state='RELEASED', disconnected_at=NULL, cycle_id=NULL, updated_at=:now
                            WHERE reservation_id=:reservation_id AND state='ENDING'
                            """
                        ),
                        {"reservation_id": reservation_id, "now": now},
                    )
                    return

                result = conn.execute(
                    self.sql_text(
                        """
                        UPDATE reservation_session_lifecycle
                        SET state='ENDED', disconnected_at=NULL, cycle_id=NULL, updated_at=:now
                        WHERE reservation_id=:reservation_id
                        """
                    ),
                    {"reservation_id": reservation_id, "now": now},
                )
                if result.rowcount:
                    return
                if conn.dialect.name == "mysql":
                    statement = """
                        INSERT INTO reservation_session_lifecycle (reservation_id, lab_id, state, updated_at)
                        VALUES (:reservation_id, :lab_id, 'ENDED', :now)
                        ON DUPLICATE KEY UPDATE state='ENDED', disconnected_at=NULL,
                            cycle_id=NULL, updated_at=VALUES(updated_at)
                    """
                else:
                    statement = """
                        INSERT INTO reservation_session_lifecycle (reservation_id, lab_id, state, updated_at)
                        VALUES (:reservation_id, :lab_id, 'ENDED', :now)
                        ON CONFLICT(reservation_id) DO UPDATE SET state='ENDED',
                            disconnected_at=NULL, cycle_id=NULL, updated_at=excluded.updated_at
                    """
                conn.execute(
                    self.sql_text(statement),
                    {"reservation_id": reservation_id, "lab_id": lab_id, "now": now},
                )
        except Exception as exc:
            self.logger.error(
                "Unable to persist reservation lifecycle state for %s: %s",
                reservation_id,
                exc,
            )

    def _last_end_release_succeeded(
        self,
        reservation_id: str,
        action: str = "scheduler:end",
    ) -> Optional[bool]:
        if not self.engine:
            return None
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    self.sql_text(
                        """
                        SELECT success, payload
                        FROM reservation_operations
                        WHERE reservation_id = :reservation_id
                          AND action = :action
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"reservation_id": reservation_id, "action": action},
                ).mappings().first()
            if not row or bool(row.get("success")):
                return None
            payload = row.get("payload")
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, Mapping):
                return None
            response = payload.get("response")
            steps = response.get("steps") if isinstance(response, Mapping) else None
            if not isinstance(steps, list):
                return None
            release_steps = [step for step in steps if isinstance(step, Mapping) and step.get("action") == "release"]
            if not release_steps:
                return None
            return bool(release_steps[-1].get("success"))
        except Exception as exc:
            self.logger.warning("Unable to inspect prior reservation end result for %s: %s", reservation_id, exc)
            return None

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
        self.record_operation(
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
        # In projection mode the remote backend is authoritative and the local
        # operation journal provides idempotency. Never mutate a local mirror
        # that may not exist in Lite mode.
        if self.projection_url or not self.engine or not current_status:
            return
        allowed = {
            ("CONFIRMED", "ACTIVE"),
            ("CONFIRMED", "COMPLETED"),
            ("ACTIVE", "COMPLETED"),
            ("CONFIRMED", "CANCELLED"),
            ("ACTIVE", "CANCELLED"),
        }
        if (current_status, new_status) not in allowed:
            self.logger.debug(
                "Skipping status transition %s -> %s for %s (not allowed)",
                current_status,
                new_status,
                reservation_id,
            )
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    self.sql_text(
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
            self.logger.error(
                "Failed to update reservation %s status to %s: %s",
                reservation_id,
                new_status,
                exc,
            )


__all__ = ["ReservationOrchestrator"]
