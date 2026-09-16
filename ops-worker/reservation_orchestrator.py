"""Reservation automation orchestration with explicit runtime dependencies."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Connection


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
        dispatch_start: Callable[[Dict[str, Any]], Any],
        dispatch_end: Callable[[Dict[str, Any]], Any],
        resolve_host_by_lab: Callable[[str], Optional[Mapping[str, Any]]],
        record_operation: Callable[..., Any],
        logger: Any,
        now: Callable[[], datetime],
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
        self.get_env = get_env
        self.enabled = parse_bool(get_env("OPS_RESERVATION_AUTOMATION", False), False)
        self.scan_interval = int(get_env("OPS_RESERVATION_SCAN_INTERVAL", "30"))
        self.start_lead = int(get_env("OPS_RESERVATION_START_LEAD", "120"))
        self.end_delay = int(get_env("OPS_RESERVATION_END_DELAY", "60"))
        self.lookback = int(get_env("OPS_RESERVATION_LOOKBACK", "21600"))
        self.retry_cooldown = int(get_env("OPS_RESERVATION_RETRY_COOLDOWN", "60"))
        self.projection_url = str(get_env("RESERVATION_PROJECTION_URL", "") or "").strip().rstrip("/")
        self.projection_gateway_id = str(get_env("RESERVATION_PROJECTION_GATEWAY_ID", "") or "").strip().lower()
        self.projection_token = env_or_secret_file("RESERVATION_PROJECTION_TOKEN")
        if self.projection_url and not (self.projection_gateway_id and self.projection_token):
            self.logger.error(
                "Reservation projection is configured but gateway ID or token is missing; "
                "remote reservation automation will remain unavailable"
            )

    def register(self, scheduler: BackgroundScheduler) -> int:
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
            "Reservation orchestrator enabled (scan=%ss, lead=%ss, end_delay=%ss)",
            self.scan_interval,
            self.start_lead,
            self.end_delay,
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
                    start_rows = self._fetch_start_candidates(conn, now)
                    end_rows = self._fetch_end_candidates(conn, now)
        except Exception as exc:
            self.logger.error("Reservation orchestrator query failed: %s", exc)
            return

        for row in start_rows:
            self._dispatch_start(dict(row))
        for row in end_rows:
            self._dispatch_end(dict(row))

    def _fetch_remote_candidates(self, now: datetime) -> List[Dict[str, Any]]:
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

        rows: List[Dict[str, Any]] = []
        for item in reservations:
            if not isinstance(item, dict):
                continue
            transaction_hash = str(item.get("transactionHash") or item.get("transaction_hash") or "").strip()
            lab_id = str(item.get("labId") or item.get("lab_id") or "").strip()
            status = str(item.get("status") or "").strip().upper()
            start_time = self.parse_reservation_datetime(item.get("startTime") or item.get("start_time"))
            end_time = self.parse_reservation_datetime(item.get("endTime") or item.get("end_time"))
            if not transaction_hash or not lab_id or status not in {"CONFIRMED", "ACTIVE"}:
                continue
            if start_time is None or end_time is None:
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
        ready_time = now - timedelta(seconds=self.end_delay)
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
        
        ready_time = now - timedelta(seconds=self.end_delay)
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
        lab_id = row.get("lab_id")
        host = self.resolve_host_by_lab(lab_id)
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
        }
        response, status_code = self.dispatch_start(payload)
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
        host = self.resolve_host_by_lab(lab_id)
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            self.logger.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "end", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        response, status_code = self.dispatch_end(payload)
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
