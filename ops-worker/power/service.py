"""Runtime assembly for configured power controllers and lab policies."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from power.models import LabPowerPolicy, ValidationError

from .executor import OperationRecorder, PowerPolicyExecutor
from .persistence import PowerOperationStore
from .registry import CredentialResolver, PowerRegistry


class PowerConfigError(RuntimeError):
    """Raised when the provider-local power catalog cannot be persisted."""


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise PowerConfigError("power configuration permissions could not be secured") from exc


LOGGER = logging.getLogger(__name__)


class PowerRuntime:
    def __init__(
        self,
        registry: PowerRegistry,
        policies: Mapping[str, LabPowerPolicy],
        *,
        record_operation: Optional[OperationRecorder] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        operation_store: Optional[PowerOperationStore] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.registry = registry
        self.policies = dict(policies)
        self.config_path = config_path
        self._config_lock = threading.RLock()
        self.executor = PowerPolicyExecutor(
            registry,
            record_operation=record_operation,
            sleep_fn=sleep_fn,
            operation_store=operation_store,
        )

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        record_operation: Optional[OperationRecorder] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        operation_store: Optional[PowerOperationStore] = None,
        credential_resolver: Optional[CredentialResolver] = None,
        config_path: Optional[Path] = None,
    ) -> "PowerRuntime":
        registry = PowerRegistry.from_config(
            config,
            sleep_fn=sleep_fn,
            credential_resolver=credential_resolver,
        )
        raw_policies = config.get("policies", [])
        if not isinstance(raw_policies, list):
            raise ValidationError("policies must be an array")
        policies: Dict[str, LabPowerPolicy] = {}
        for raw_policy in raw_policies:
            policy = LabPowerPolicy.from_mapping(raw_policy)
            if policy.lab_id in policies:
                raise ValidationError(f"duplicate policy for lab {policy.lab_id}")
            policies[policy.lab_id] = policy
        return cls(
            registry,
            policies,
            record_operation=record_operation,
            sleep_fn=sleep_fn,
            operation_store=operation_store,
            config_path=config_path,
        )

    @classmethod
    def from_path(
        cls,
        path: str,
        *,
        record_operation: Optional[OperationRecorder] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        operation_store: Optional[PowerOperationStore] = None,
        credential_resolver: Optional[CredentialResolver] = None,
    ) -> "PowerRuntime":
        config_path = Path(path)
        if not config_path.exists():
            return cls.from_config(
                {"controllers": [], "outlets": [], "policies": []},
                record_operation=record_operation,
                sleep_fn=sleep_fn,
                operation_store=operation_store,
                credential_resolver=credential_resolver,
                config_path=config_path,
            )
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError("power configuration could not be read") from exc
        return cls.from_config(
            config,
            record_operation=record_operation,
            sleep_fn=sleep_fn,
            operation_store=operation_store,
            credential_resolver=credential_resolver,
            config_path=config_path,
        )

    def execute_policy(
        self,
        lab_id: str,
        reservation_id: str,
        phase: str,
        *,
        actor: str,
        dry_run: bool = False,
        local_mode: bool = False,
    ) -> Dict[str, Any]:
        policy = self.policies.get(str(lab_id))
        if policy is None:
            return {
                "success": True,
                "status": "no_policy",
                "phase": phase,
                "steps": [],
            }
        if policy.respect_local_mode and local_mode:
            return {
                "success": True,
                "status": "skipped_local_mode",
                "phase": phase,
                "steps": [],
            }
        result = self.executor.execute_phase(
            policy,
            reservation_id,
            phase,
            actor=actor,
            dry_run=dry_run,
        )
        if not result["success"]:
            failure_mode = (
                policy.start_failure_mode
                if phase in {"pre_start", "start", "post_start"}
                else policy.end_failure_mode
            )
            if failure_mode == "warn_and_continue":
                return {
                    **result,
                    "success": True,
                    "status": "completed_with_warnings",
                }
        return result

    def reset_mock(self) -> int:
        reset_count = 0
        for controller in self.registry.all():
            reset = getattr(controller.driver, "reset", None)
            if controller.definition.driver_name == "mock" and callable(reset):
                reset()
                reset_count += 1
        if reset_count:
            self.executor.reset_idempotency()
        return reset_count

    def execute_manual(self, **kwargs: Any) -> Dict[str, Any]:
        return self.executor.execute_manual(**kwargs)

    def describe_controllers(self):
        return [
            self.registry.public_description(controller)
            for controller in self.registry.all()
        ]

    def describe_policies(self):
        return [
            self.policies[lab_id].to_dict()
            for lab_id in sorted(self.policies)
        ]

    def update_policy(self, raw_policy: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate, persist and activate one provider-local lab policy."""
        policy = LabPowerPolicy.from_mapping(raw_policy)
        if self.config_path is None:
            raise PowerConfigError("power configuration persistence is not configured")

        with self._config_lock:
            config = self._read_config_for_update()
            policies = []
            replaced = False
            for existing in self.policies.values():
                if existing.lab_id == policy.lab_id:
                    policies.append(policy.to_dict())
                    replaced = True
                else:
                    policies.append(existing.to_dict())
            if not replaced:
                policies.append(policy.to_dict())
            config["policies"] = policies
            self._write_config(config)
            self.policies[policy.lab_id] = policy
        return policy.to_dict()

    def _read_config_for_update(self) -> Dict[str, Any]:
        assert self.config_path is not None
        if not self.config_path.exists():
            return {"controllers": [], "outlets": [], "policies": []}
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise PowerConfigError("power configuration could not be read") from exc
        if not isinstance(config, dict):
            raise PowerConfigError("power configuration must be an object")
        return config

    def _write_config(self, config: Mapping[str, Any]) -> None:
        assert self.config_path is not None
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Optional[Path] = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.config_path.parent,
                prefix=f".{self.config_path.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            _secure_file(temporary)
            os.replace(temporary, self.config_path)
            temporary = None
            _secure_file(self.config_path)
        except OSError as exc:
            raise PowerConfigError("power configuration could not be written") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    LOGGER.warning("Unable to remove temporary power configuration file")

    def operations(self, reservation_id: Optional[str] = None):
        if self.executor.operation_store is not None:
            durable = self.executor.operation_store.list(reservation_id=reservation_id)
            if durable is not None:
                return durable
        return self.executor.operations(reservation_id)
