"""Policy execution, safety checks, idempotency and operation reporting."""

from __future__ import annotations

import hashlib
import logging
import time
from threading import RLock
from typing import Any, Callable, Dict, List, Optional

from power.models import LabPowerPolicy, PowerPolicyStep, ValidationError

from .drivers.base import PowerDriverError
from .registry import PowerRegistry, RegisteredController


OperationRecorder = Callable[[Dict[str, Any]], None]


class PowerPolicyExecutor:
    def __init__(
        self,
        registry: PowerRegistry,
        *,
        record_operation: Optional[OperationRecorder] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        operation_store: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self._record_operation = record_operation
        self._sleep = sleep_fn or time.sleep
        self._operation_store = operation_store
        self._completed: Dict[str, Dict[str, Any]] = {}
        self._operations: List[Dict[str, Any]] = []
        self._lock = RLock()

    def operations(self, reservation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            operations = list(self._operations)
        if reservation_id:
            operations = [
                operation
                for operation in operations
                if operation.get("reservationId") == reservation_id
            ]
        return list(reversed(operations))

    @property
    def operation_store(self) -> Optional[Any]:
        return self._operation_store

    def execute_phase(
        self,
        policy: LabPowerPolicy,
        reservation_id: str,
        phase: str,
        *,
        actor: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        reservation_id = self._required_identifier(reservation_id, "reservationId", 128)
        actor = self._required_identifier(actor, "actor", 128)
        steps = policy.steps_for_phase(phase)
        self._preflight(steps, maintenance_mode=policy.maintenance_mode)
        if not policy.enabled:
            return {
                "success": True,
                "status": "policy_disabled",
                "phase": phase,
                "steps": [],
            }
        if dry_run:
            return {
                "success": True,
                "status": "dry_run",
                "phase": phase,
                "steps": [
                    {
                        "success": True,
                        "status": "dry_run",
                        "phase": step.phase,
                        "controllerId": step.controller_id,
                        "outlet": step.outlet,
                        "action": step.action,
                        "required": step.required,
                    }
                    for step in steps
                ],
            }

        results: List[Dict[str, Any]] = []
        success = True
        has_warnings = False
        for step in steps:
            key = self._idempotency_key(
                reservation_id,
                policy.lab_id,
                phase,
                policy.policy_id or policy.name,
                step,
            )
            with self._lock:
                existing = self._completed.get(key)
                if existing is None and self._operation_store is not None:
                    existing = self._operation_store.get_successful(key)
                    if existing is not None:
                        self._completed[key] = existing
                if existing is not None:
                    results.append({**existing, "status": "skipped_already_completed"})
                    continue
                result = self._execute_step(
                    step,
                    reservation_id=reservation_id,
                    lab_id=policy.lab_id,
                    idempotency_key=key,
                    actor=actor,
                    policy_id=policy.policy_id or policy.name,
                    step_id=step.step_id or str(step.sequence),
                )
            results.append(result)
            if not result["success"] and step.required:
                success = False
                break
            if not result["success"]:
                has_warnings = True

        return {
            "success": success,
            "status": (
                "failed"
                if not success
                else "completed_with_warnings"
                if has_warnings
                else "completed"
            ),
            "phase": phase,
            "steps": results,
        }

    def execute_manual(
        self,
        *,
        controller_id: str,
        outlet_id: str,
        action: str,
        actor: str,
        idempotency_key: str,
        reason: Optional[str] = None,
        off_seconds: int = 10,
        allow_protected: bool = False,
        maintenance: bool = False,
    ) -> Dict[str, Any]:
        controller_id = self._required_identifier(controller_id, "controllerId", 128)
        outlet_id = self._required_identifier(outlet_id, "outlet", 64)
        actor = self._required_identifier(actor, "actor", 128)
        reason = str(reason or "").strip() or None
        if reason is not None and len(reason) > 256:
            raise ValidationError("reason is too long")
        action = str(action or "").strip().lower()
        if action not in {"on", "off", "cycle"}:
            raise ValidationError("action must be on, off, or cycle")
        controller, outlet = self.registry.get_outlet(controller_id, outlet_id)
        self._check_enabled(controller)
        if outlet.protected and not (allow_protected and maintenance):
            raise PermissionError("protected outlet requires allowProtected and maintenance")
        if action == "cycle" and not 1 <= int(off_seconds) <= 3600:
            raise ValidationError("offSeconds must be between 1 and 3600")
        step = PowerPolicyStep.from_mapping(
            {
                "phase": "manual",
                "sequence": 1,
                "controllerId": controller_id,
                "outlet": outlet_id,
                "action": action,
                "offSeconds": off_seconds,
                "readBackRequired": True,
                "allowProtected": allow_protected,
            }
        )
        key = self._required_identifier(idempotency_key, "idempotencyKey", 128)
        with self._lock:
            existing = self._completed.get(key)
            if existing is None and self._operation_store is not None:
                existing = self._operation_store.get_successful(key)
                if existing is not None:
                    self._completed[key] = existing
            if existing is not None:
                return {**existing, "status": "skipped_already_completed"}
            return self._execute_step(
                step,
                reservation_id=f"manual:{hashlib.sha256(key.encode('utf-8')).hexdigest()}",
                lab_id=None,
                idempotency_key=key,
                actor=actor,
                policy_id="manual",
                step_id=None,
                reason=reason,
            )

    def reset_idempotency(self) -> None:
        with self._lock:
            self._completed.clear()

    def _preflight(self, steps: List[PowerPolicyStep], *, maintenance_mode: bool = False) -> None:
        for step in steps:
            controller, outlet = self.registry.get_outlet(step.controller_id, step.outlet)
            self._check_enabled(controller)
            self._check_capabilities(controller, step)
            if outlet.protected and not (step.allow_protected and maintenance_mode):
                raise PermissionError(
                    f"protected outlet '{step.outlet}' requires allowProtected and maintenanceMode"
                )

    @staticmethod
    def _check_enabled(controller: RegisteredController) -> None:
        if not controller.definition.enabled:
            raise ValidationError(f"controller '{controller.definition.id}' is disabled")

    @staticmethod
    def _check_capabilities(controller: RegisteredController, step: PowerPolicyStep) -> None:
        capabilities = controller.driver.capabilities
        if not capabilities.per_outlet_switching:
            raise ValidationError(
                f"controller '{controller.definition.id}' does not support per-outlet switching"
            )
        if step.action == "cycle" and not capabilities.power_cycle:
            raise ValidationError(
                f"controller '{controller.definition.id}' does not support power cycle"
            )
        if step.read_back_required and not capabilities.read_back_state:
            raise ValidationError(
                f"controller '{controller.definition.id}' does not support required readback"
            )

    @staticmethod
    def _required_identifier(value: Any, field_name: str, max_length: int) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValidationError(f"{field_name} is required")
        if len(normalized) > max_length:
            raise ValidationError(f"{field_name} is too long")
        return normalized

    @staticmethod
    def _idempotency_key(
        reservation_id: str,
        lab_id: str,
        phase: str,
        policy_id: str,
        step: PowerPolicyStep,
    ) -> str:
        step_id = step.step_id or str(step.sequence)
        raw_key = f"{reservation_id}:{lab_id}:{phase}:{policy_id}:{step_id}:{step.action}"
        if len(raw_key) <= 255:
            return raw_key
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return f"{raw_key[:186]}:{digest}"

    def _execute_step(
        self,
        step: PowerPolicyStep,
        *,
        reservation_id: str,
        lab_id: Optional[str],
        idempotency_key: str,
        actor: str,
        policy_id: Optional[str] = None,
        step_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        controller, outlet = self.registry.get_outlet(step.controller_id, step.outlet)
        self._check_enabled(controller)
        self._check_capabilities(controller, step)
        if outlet.protected and not step.allow_protected:
            raise PermissionError(f"protected outlet '{step.outlet}' requires allowProtected")

        started = time.monotonic()
        before: Optional[str] = None
        after: Optional[str] = None
        message: Optional[str] = None
        success = False
        status = "failed"
        try:
            supports_readback = controller.driver.capabilities.read_back_state
            if supports_readback:
                before = controller.driver.get_outlet_state(step.outlet).get("state")
            if step.action in {"on", "off"} and before == step.desired_state:
                after = before
                success = True
                status = "skipped_already_in_state"
            else:
                if step.delay_before_seconds:
                    self._sleep(step.delay_before_seconds)
                attempts = max(1, step.retry_count + 1)
                last_error: Optional[Exception] = None
                for _attempt in range(attempts):
                    try:
                        if step.action == "cycle":
                            controller.driver.cycle_outlet(
                                step.outlet,
                                off_seconds=step.off_seconds,
                                timeout_seconds=max(30, step.timeout_seconds),
                            )
                        else:
                            controller.driver.set_outlet_state(
                                step.outlet,
                                step.action,
                                timeout_seconds=step.timeout_seconds,
                            )
                        last_error = None
                        break
                    except PowerDriverError as exc:
                        last_error = exc
                if last_error is not None:
                    raise last_error
                if supports_readback:
                    after = controller.driver.get_outlet_state(step.outlet).get("state")
                if step.read_back_required and step.desired_state and after != step.desired_state:
                    raise PowerDriverError(
                        f"readback for outlet '{step.outlet}' was '{after}', expected '{step.desired_state}'"
                    )
                success = True
                status = "completed"
                if step.delay_after_seconds:
                    self._sleep(step.delay_after_seconds)
        except (PowerDriverError, ValidationError, PermissionError) as exc:
            logging.warning(
                "Power operation failed error=%s",
                type(exc).__name__,
            )
            message = "Power controller operation failed"
        duration_ms = int((time.monotonic() - started) * 1000)
        result = {
            "reservationId": reservation_id,
            "labId": lab_id,
            "phase": step.phase,
            "controllerId": controller.definition.id,
            "outlet": step.outlet,
            "action": step.action,
            "policyId": policy_id,
            "stepId": step_id,
            "desiredState": step.desired_state,
            "required": step.required,
            "success": success,
            "status": status,
            "idempotencyKey": idempotency_key,
            "observedStateBefore": before,
            "observedStateAfter": after,
            "durationMs": duration_ms,
            "actor": actor,
            "reason": reason,
            "message": message,
        }
        with self._lock:
            self._operations.append(result)
            if success:
                self._completed[idempotency_key] = result
        if self._operation_store is not None:
            self._operation_store.save(result)
        if self._record_operation is not None:
            try:
                self._record_operation(result)
            except Exception:  # pragma: no cover - persistence must not mask device outcome
                logging.exception("Unable to persist power operation")
        return result
