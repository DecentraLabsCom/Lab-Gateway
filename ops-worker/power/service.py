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

_CONTROLLER_FIELDS = frozenset(
    {"id", "name", "driver", "enabled", "host", "port", "credentialRef", "config", "outlets"}
)
_CONTROLLER_CONFIG_FIELDS = frozenset(
    {
        "profile",
        "snmpVersion",
        "timeoutSeconds",
        "retries",
        "moduleIndex",
        "path",
        "useHttps",
        "verifyTls",
    }
)


def _controller_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def _controller_int(value: Any, field_name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"{field_name} must be between {minimum} and {maximum}")
    return parsed


def _controller_payload(raw_controller: Mapping[str, Any]) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    if not isinstance(raw_controller, Mapping):
        raise ValidationError("power controller must be an object")
    unknown_fields = set(raw_controller) - _CONTROLLER_FIELDS
    if unknown_fields:
        raise ValidationError("power controller contains unsupported fields")

    controller_id = str(raw_controller.get("id") or "").strip()
    if not controller_id:
        raise ValidationError("controller id is required")
    name = str(raw_controller.get("name") or controller_id).strip()
    if not name:
        raise ValidationError("controller name is required")
    driver = str(raw_controller.get("driver") or "").strip().lower()
    if driver not in {"mock", "apc-powernet-snmp", "netio-json"}:
        raise ValidationError("unsupported power driver")

    raw_config = raw_controller.get("config") or {}
    if not isinstance(raw_config, Mapping):
        raise ValidationError("controller config must be an object")
    if set(raw_config) - _CONTROLLER_CONFIG_FIELDS:
        raise ValidationError("controller config contains unsupported fields")
    config = {key: raw_config[key] for key in _CONTROLLER_CONFIG_FIELDS if key in raw_config}
    if "profile" in config and str(config["profile"]).strip().lower() not in {"auto", "legacy", "rpdu2"}:
        raise ValidationError("controller profile is invalid")
    if "snmpVersion" in config and str(config["snmpVersion"]).strip().lower() not in {"v1", "v2c", "v3"}:
        raise ValidationError("SNMP version is invalid")
    if "timeoutSeconds" in config:
        config["timeoutSeconds"] = _controller_int(config["timeoutSeconds"], "timeoutSeconds", minimum=1, maximum=60)
    if "retries" in config:
        config["retries"] = _controller_int(config["retries"], "retries", minimum=1, maximum=10)
    if "moduleIndex" in config:
        config["moduleIndex"] = _controller_int(config["moduleIndex"], "moduleIndex", minimum=1, maximum=65535)
    if "path" in config:
        path = str(config["path"] or "").strip()
        if not path.startswith("/") or len(path) > 255 or "\n" in path or "\r" in path:
            raise ValidationError("controller API path is invalid")
        config["path"] = path
    if "useHttps" in config:
        config["useHttps"] = _controller_bool(config["useHttps"], False)
    if "verifyTls" in config:
        config["verifyTls"] = _controller_bool(config["verifyTls"], True)

    raw_outlets = raw_controller.get("outlets")
    if not isinstance(raw_outlets, list):
        raise ValidationError("controller outlets must be an array")
    outlets: list[Dict[str, Any]] = []
    seen_outlets = set()
    for raw_outlet in raw_outlets:
        if not isinstance(raw_outlet, Mapping):
            raise ValidationError("every controller outlet must be an object")
        outlet_id = str(raw_outlet.get("outlet", raw_outlet.get("outletKey")) or "").strip()
        if not outlet_id:
            raise ValidationError("outlet is required")
        if outlet_id in seen_outlets:
            raise ValidationError(f"duplicate outlet {outlet_id} for controller {controller_id}")
        seen_outlets.add(outlet_id)
        outlets.append(
            {
                "controllerId": controller_id,
                "outlet": outlet_id,
                "displayName": str(raw_outlet.get("displayName") or "").strip() or None,
                "logicalName": str(raw_outlet.get("logicalName") or "").strip() or None,
                "protected": _controller_bool(raw_outlet.get("protected"), False),
                "critical": _controller_bool(raw_outlet.get("critical"), False),
                "defaultState": str(raw_outlet.get("defaultState") or "off").strip().lower(),
            }
        )

    controller = {
        "id": controller_id,
        "name": name,
        "driver": driver,
        "enabled": _controller_bool(raw_controller.get("enabled"), True),
        "host": str(raw_controller.get("host") or "").strip() or None,
        "port": raw_controller.get("port"),
        "credentialRef": str(raw_controller.get("credentialRef") or "").strip() or None,
        "config": config,
    }
    return controller, outlets


class PowerRuntime:
    def __init__(
        self,
        registry: PowerRegistry,
        policies: Mapping[str, LabPowerPolicy],
        *,
        record_operation: Optional[OperationRecorder] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        operation_store: Optional[PowerOperationStore] = None,
        credential_resolver: Optional[CredentialResolver] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.registry = registry
        self.policies = dict(policies)
        self.config_path = config_path
        self._config_lock = threading.RLock()
        self._record_operation = record_operation
        self._sleep_fn = sleep_fn
        self._operation_store = operation_store
        self._credential_resolver = credential_resolver
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
            credential_resolver=credential_resolver,
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

    def has_controller(self, controller_id: str) -> bool:
        return any(
            controller.definition.id == str(controller_id)
            for controller in self.registry.all()
        )

    def update_controller(self, raw_controller: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate, persist and activate one provider-local controller."""
        controller, outlets = _controller_payload(raw_controller)
        if self.config_path is None:
            raise PowerConfigError("power configuration persistence is not configured")

        with self._config_lock:
            config = self._read_config_for_update()
            raw_controllers = config.get("controllers", [])
            if not isinstance(raw_controllers, list):
                raise ValidationError("controllers must be an array")
            controllers = []
            replaced = False
            for existing in raw_controllers:
                if not isinstance(existing, Mapping):
                    raise ValidationError("every power controller must be an object")
                if str(existing.get("id") or "").strip() == controller["id"]:
                    controllers.append(controller)
                    replaced = True
                else:
                    controllers.append(dict(existing))
            if not replaced:
                controllers.append(controller)

            raw_outlets = config.get("outlets", [])
            if not isinstance(raw_outlets, list):
                raise ValidationError("outlets must be an array")
            catalog_outlets = [
                dict(existing)
                for existing in raw_outlets
                if isinstance(existing, Mapping)
                and str(existing.get("controllerId", existing.get("controller_id")) or "").strip()
                != controller["id"]
            ]
            catalog_outlets.extend(outlets)
            candidate_config = dict(config)
            candidate_config["controllers"] = controllers
            candidate_config["outlets"] = catalog_outlets

            candidate_runtime = PowerRuntime.from_config(
                candidate_config,
                record_operation=self._record_operation,
                sleep_fn=self._sleep_fn,
                operation_store=self._operation_store,
                credential_resolver=self._credential_resolver,
                config_path=self.config_path,
            )
            self._write_config(candidate_config)
            self.registry = candidate_runtime.registry
            self.policies = candidate_runtime.policies
            self.executor.registry = self.registry

        return self.registry.public_description(self.registry.get(controller["id"]))

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
