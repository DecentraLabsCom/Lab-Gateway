"""Durable persistence for power operation detail and idempotency."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class PowerOperationStore:
    """Persist operation outcomes without making the device call SQL-aware."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_successful(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT reservation_id, lab_id, policy_id, step_id, phase,
                               controller_id, outlet_key, action, requested_state,
                               observed_state_before, observed_state_after, status,
                               success, response_code, duration_ms, idempotency_key,
                               payload, message, created_at
                        FROM power_operations
                        WHERE idempotency_key = :idempotency_key AND success = 1
                        LIMIT 1
                        """
                    ),
                    {"idempotency_key": idempotency_key},
                ).mappings().first()
            return self._row_to_operation(row) if row is not None else None
        except SQLAlchemyError as exc:
            self._warn_unavailable(exc)
            return None

    def save(self, operation: Dict[str, Any]) -> bool:
        values = self._values(operation)
        if not values["idempotency_key"]:
            logging.warning("Skipping power operation without idempotency key")
            return False
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO power_operations (
                            reservation_id, lab_id, policy_id, step_id, phase,
                            controller_id, outlet_key, action, requested_state,
                            observed_state_before, observed_state_after, status,
                            success, response_code, duration_ms, idempotency_key,
                            payload, message, created_at
                        ) VALUES (
                            :reservation_id, :lab_id, :policy_id, :step_id, :phase,
                            :controller_id, :outlet_key, :action, :requested_state,
                            :observed_state_before, :observed_state_after, :status,
                            :success, :response_code, :duration_ms, :idempotency_key,
                            :payload, :message, :created_at
                        )
                        """
                    ),
                    values,
                )
            return True
        except IntegrityError:
            return self._update_existing(values)
        except SQLAlchemyError as exc:
            self._warn_unavailable(exc)
            return False

    def list(
        self,
        *,
        reservation_id: Optional[str] = None,
        limit: int = 100,
    ) -> Optional[List[Dict[str, Any]]]:
        bounded_limit = max(1, min(int(limit), 500))
        query = """
            SELECT reservation_id, lab_id, policy_id, step_id, phase,
                   controller_id, outlet_key, action, requested_state,
                   observed_state_before, observed_state_after, status,
                   success, response_code, duration_ms, idempotency_key,
                   payload, message, created_at
            FROM power_operations
        """
        parameters: Dict[str, Any] = {"limit": bounded_limit}
        if reservation_id:
            query += " WHERE reservation_id = :reservation_id"
            parameters["reservation_id"] = reservation_id
        query += " ORDER BY id DESC LIMIT :limit"
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(query), parameters).mappings().all()
            return [self._row_to_operation(row) for row in rows]
        except SQLAlchemyError as exc:
            self._warn_unavailable(exc)
            return None

    def _update_existing(self, values: Dict[str, Any]) -> bool:
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE power_operations
                        SET reservation_id = :reservation_id,
                            lab_id = :lab_id,
                            policy_id = :policy_id,
                            step_id = :step_id,
                            phase = :phase,
                            controller_id = :controller_id,
                            outlet_key = :outlet_key,
                            action = :action,
                            requested_state = :requested_state,
                            observed_state_before = :observed_state_before,
                            observed_state_after = :observed_state_after,
                            status = :status,
                            success = :success,
                            response_code = :response_code,
                            duration_ms = :duration_ms,
                            payload = :payload,
                            message = :message
                        WHERE idempotency_key = :idempotency_key
                        """
                    ),
                    values,
                )
            return True
        except SQLAlchemyError as exc:
            self._warn_unavailable(exc)
            return False

    @staticmethod
    def _values(operation: Dict[str, Any]) -> Dict[str, Any]:
        action = str(operation.get("action") or "").strip().lower()
        return {
            "reservation_id": operation.get("reservationId"),
            "lab_id": operation.get("labId"),
            "policy_id": operation.get("policyId"),
            "step_id": operation.get("stepId"),
            "phase": operation.get("phase"),
            "controller_id": operation.get("controllerId"),
            "outlet_key": operation.get("outlet"),
            "action": action,
            "requested_state": operation.get("desiredState") or (action if action in {"on", "off"} else None),
            "observed_state_before": operation.get("observedStateBefore"),
            "observed_state_after": operation.get("observedStateAfter"),
            "status": operation.get("status") or "failed",
            "success": bool(operation.get("success")),
            "response_code": operation.get("responseCode") or (200 if operation.get("success") else 502),
            "duration_ms": operation.get("durationMs"),
            "idempotency_key": str(operation.get("idempotencyKey") or "").strip(),
            "payload": json.dumps(operation, default=str, separators=(",", ":")),
            "message": operation.get("message"),
            "created_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _row_to_operation(row: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        raw_payload = row.get("payload") if row is not None else None
        if raw_payload:
            try:
                decoded = json.loads(raw_payload)
                if isinstance(decoded, dict):
                    payload = decoded
            except (TypeError, ValueError):
                payload = {}
        result = {
            "reservationId": row.get("reservation_id"),
            "labId": row.get("lab_id"),
            "policyId": row.get("policy_id"),
            "stepId": row.get("step_id"),
            "phase": row.get("phase"),
            "controllerId": row.get("controller_id"),
            "outlet": row.get("outlet_key"),
            "action": row.get("action"),
            "success": bool(row.get("success")),
            "status": row.get("status"),
            "idempotencyKey": row.get("idempotency_key"),
            "observedStateBefore": row.get("observed_state_before"),
            "observedStateAfter": row.get("observed_state_after"),
            "durationMs": row.get("duration_ms"),
            "actor": payload.get("actor"),
            "reason": payload.get("reason"),
            "message": row.get("message"),
            "createdAt": row.get("created_at"),
        }
        return result

    @staticmethod
    def _warn_unavailable(exc: SQLAlchemyError) -> None:
        logging.warning(
            "Power operation persistence unavailable: %s",
            type(exc).__name__,
        )
