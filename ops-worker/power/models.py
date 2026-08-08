"""Validated domain models for provider-local power policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


class ValidationError(ValueError):
    """Raised when an energy controller or policy is unsafe or malformed."""


POWER_PHASES = frozenset(
    {
        "pre_start",
        "start",
        "post_start",
        "pre_end",
        "end",
        "post_end",
        "manual",
        "maintenance",
        "emergency_stop",
    }
)
POWER_ACTIONS = frozenset({"on", "off", "cycle"})
POWER_STATES = frozenset({"on", "off", "unknown"})
POWER_FAILURE_MODES = frozenset({"fail_reservation_start", "warn_and_continue"})


def _text(value: Any, field_name: str, *, max_length: int = 160) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValidationError(f"{field_name} is required")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} is too long")
    return value


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def _non_negative_int(value: Any, field_name: str, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed < 0 or parsed > maximum:
        raise ValidationError(f"{field_name} must be between 0 and {maximum}")
    return parsed


@dataclass
class PowerCapabilities:
    per_outlet_switching: bool = False
    read_back_state: bool = False
    power_cycle: bool = False
    delayed_actions: bool = False
    aggregate_metering: bool = False
    per_outlet_metering: bool = False
    snmp_v1: bool = False
    snmp_v2c: bool = False
    snmp_v3: bool = False
    https_api: bool = False
    mqtt: bool = False
    modbus_tcp: bool = False

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "PowerCapabilities":
        source = value or {}
        aliases = {
            "per_outlet_switching": "perOutletSwitching",
            "read_back_state": "readBackState",
            "power_cycle": "powerCycle",
            "delayed_actions": "delayedActions",
            "aggregate_metering": "aggregateMetering",
            "per_outlet_metering": "perOutletMetering",
            "snmp_v1": "snmpV1",
            "snmp_v2c": "snmpV2c",
            "snmp_v3": "snmpV3",
            "https_api": "httpsApi",
            "modbus_tcp": "modbusTcp",
        }
        values = {
            field_name: _bool(source.get(json_name, source.get(field_name)), False)
            for field_name, json_name in aliases.items()
        }
        return cls(**values)

    def to_dict(self) -> Dict[str, bool]:
        return {
            "perOutletSwitching": self.per_outlet_switching,
            "readBackState": self.read_back_state,
            "powerCycle": self.power_cycle,
            "delayedActions": self.delayed_actions,
            "aggregateMetering": self.aggregate_metering,
            "perOutletMetering": self.per_outlet_metering,
            "snmpV1": self.snmp_v1,
            "snmpV2c": self.snmp_v2c,
            "snmpV3": self.snmp_v3,
            "httpsApi": self.https_api,
            "mqtt": self.mqtt,
            "modbusTcp": self.modbus_tcp,
        }


@dataclass
class PowerOutlet:
    controller_id: str
    outlet_key: str
    display_name: Optional[str] = None
    logical_name: Optional[str] = None
    protected: bool = False
    critical: bool = False
    default_state: str = "off"

    def __post_init__(self) -> None:
        self.controller_id = _text(self.controller_id, "controllerId", max_length=128)
        self.outlet_key = _text(self.outlet_key, "outlet", max_length=64)
        if self.default_state not in {"on", "off"}:
            raise ValidationError("defaultState must be on or off")

    def to_dict(self, state: str = "unknown") -> Dict[str, Any]:
        return {
            "outlet": self.outlet_key,
            "displayName": self.display_name,
            "logicalName": self.logical_name,
            "protected": self.protected,
            "critical": self.critical,
            "state": state,
        }


@dataclass
class PowerController:
    id: str
    name: str
    driver_name: str
    enabled: bool = True
    host: Optional[str] = None
    port: Optional[int] = None
    credential_ref: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _text(self.id, "controllerId", max_length=128)
        self.name = _text(self.name, "name", max_length=160)
        self.driver_name = _text(self.driver_name, "driver", max_length=64).lower()
        if self.port is not None:
            try:
                self.port = int(self.port)
            except (TypeError, ValueError) as exc:
                raise ValidationError("port must be an integer") from exc
            if not 1 <= self.port <= 65535:
                raise ValidationError("port must be between 1 and 65535")


@dataclass
class PowerPolicyStep:
    phase: str
    sequence: int
    controller_id: str
    outlet: str
    action: str
    step_id: Optional[str] = None
    logical_name: Optional[str] = None
    desired_state: Optional[str] = None
    required: bool = True
    read_back_required: bool = True
    off_seconds: int = 10
    delay_before_seconds: int = 0
    delay_after_seconds: int = 0
    timeout_seconds: int = 20
    retry_count: int = 0
    allow_protected: bool = False
    conditions: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PowerPolicyStep":
        if not isinstance(value, Mapping):
            raise ValidationError("every policy step must be an object")
        phase = _text(value.get("phase"), "phase", max_length=32).lower()
        if phase not in POWER_PHASES:
            raise ValidationError(f"unsupported power phase: {phase}")
        sequence = _non_negative_int(value.get("sequence"), "sequence", default=0, maximum=1_000_000)
        controller_id = _text(value.get("controllerId", value.get("controller_id")), "controllerId", max_length=128)
        outlet = _text(value.get("outlet", value.get("outletKey", value.get("outlet_key"))), "outlet", max_length=64)
        action = _text(value.get("action"), "action", max_length=16).lower()
        if action not in POWER_ACTIONS:
            raise ValidationError(f"unsupported power action: {action}")

        desired_state = value.get("desiredState", value.get("desired_state"))
        if desired_state is None and action in {"on", "off"}:
            desired_state = action
        if desired_state is not None:
            desired_state = _text(desired_state, "desiredState", max_length=16).lower()
            if desired_state not in {"on", "off", "unknown"}:
                raise ValidationError("desiredState must be on, off, or unknown")

        off_seconds = _non_negative_int(
            value.get("offSeconds", value.get("off_seconds")),
            "offSeconds",
            default=10,
            maximum=3600,
        )
        if action == "cycle" and off_seconds == 0:
            raise ValidationError("offSeconds must be greater than zero for cycle")

        return cls(
            phase=phase,
            sequence=sequence,
            controller_id=controller_id,
            outlet=outlet,
            action=action,
            step_id=(str(value.get("id") or value.get("stepId") or "").strip() or None),
            logical_name=(str(value.get("logicalName") or value.get("logical_name") or "").strip() or None),
            desired_state=desired_state,
            required=_bool(value.get("required"), True),
            read_back_required=_bool(value.get("readBackRequired", value.get("read_back_required")), True),
            off_seconds=off_seconds,
            delay_before_seconds=_non_negative_int(
                value.get("delayBeforeSeconds", value.get("delay_before_seconds")),
                "delayBeforeSeconds",
                default=0,
                maximum=3600,
            ),
            delay_after_seconds=_non_negative_int(
                value.get("delayAfterSeconds", value.get("delay_after_seconds")),
                "delayAfterSeconds",
                default=0,
                maximum=3600,
            ),
            timeout_seconds=_non_negative_int(
                value.get("timeoutSeconds", value.get("timeout_seconds")),
                "timeoutSeconds",
                default=20,
                maximum=300,
            ),
            retry_count=_non_negative_int(
                value.get("retryCount", value.get("retry_count")),
                "retryCount",
                default=0,
                maximum=5,
            ),
            allow_protected=_bool(value.get("allowProtected", value.get("allow_protected")), False),
            conditions=(
                dict(value.get("conditions"))
                if isinstance(value.get("conditions"), Mapping)
                else {}
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.step_id,
            "phase": self.phase,
            "sequence": self.sequence,
            "controllerId": self.controller_id,
            "outlet": self.outlet,
            "logicalName": self.logical_name,
            "action": self.action,
            "desiredState": self.desired_state,
            "required": self.required,
            "readBackRequired": self.read_back_required,
            "offSeconds": self.off_seconds,
            "delayBeforeSeconds": self.delay_before_seconds,
            "delayAfterSeconds": self.delay_after_seconds,
            "timeoutSeconds": self.timeout_seconds,
            "retryCount": self.retry_count,
            "allowProtected": self.allow_protected,
            "conditions": self.conditions,
        }


@dataclass
class LabPowerPolicy:
    lab_id: str
    name: str
    steps: List[PowerPolicyStep]
    policy_id: Optional[str] = None
    enabled: bool = True
    respect_local_mode: bool = True
    maintenance_mode: bool = False
    start_failure_mode: str = "fail_reservation_start"
    end_failure_mode: str = "warn_and_continue"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LabPowerPolicy":
        if not isinstance(value, Mapping):
            raise ValidationError("every power policy must be an object")
        lab_id = _text(value.get("labId", value.get("lab_id")), "labId", max_length=128)
        name = _text(value.get("policyName", value.get("name")), "policyName", max_length=160)
        start_failure_mode = str(value.get("startFailureMode") or "fail_reservation_start").strip().lower()
        end_failure_mode = str(value.get("endFailureMode") or "warn_and_continue").strip().lower()
        if start_failure_mode not in POWER_FAILURE_MODES:
            raise ValidationError(f"unsupported startFailureMode: {start_failure_mode}")
        if end_failure_mode not in POWER_FAILURE_MODES:
            raise ValidationError(f"unsupported endFailureMode: {end_failure_mode}")

        steps = [PowerPolicyStep.from_mapping(step) for step in value.get("steps", [])]
        seen = set()
        for step in steps:
            key = (step.phase, step.sequence)
            if key in seen:
                raise ValidationError(
                    f"duplicate sequence {step.sequence} in phase {step.phase}"
                )
            seen.add(key)
        return cls(
            lab_id=lab_id,
            name=name,
            steps=steps,
            policy_id=(str(value.get("id") or "").strip() or None),
            enabled=_bool(value.get("enabled"), True),
            respect_local_mode=_bool(value.get("respectLocalMode", value.get("respect_local_mode")), True),
            maintenance_mode=_bool(value.get("maintenanceMode", value.get("maintenance_mode")), False),
            start_failure_mode=start_failure_mode,
            end_failure_mode=end_failure_mode,
        )

    def steps_for_phase(self, phase: str) -> List[PowerPolicyStep]:
        normalized = str(phase or "").strip().lower()
        if normalized not in POWER_PHASES:
            raise ValidationError(f"unsupported power phase: {normalized}")
        return sorted(
            (step for step in self.steps if step.phase == normalized),
            key=lambda step: step.sequence,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.policy_id,
            "labId": self.lab_id,
            "policyName": self.name,
            "enabled": self.enabled,
            "respectLocalMode": self.respect_local_mode,
            "maintenanceMode": self.maintenance_mode,
            "startFailureMode": self.start_failure_mode,
            "endFailureMode": self.end_failure_mode,
            "steps": [step.to_dict() for step in self.steps],
        }
