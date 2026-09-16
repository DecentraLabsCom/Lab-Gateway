"""Controller registry and safe public descriptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from power.models import PowerCapabilities, PowerController, PowerOutlet, ValidationError

from .drivers.base import PowerDriver, PowerDriverError
from .drivers.apc_snmp import ApcPowerNetSnmpDriver
from .drivers.mock import MockPowerDriver
from .drivers.netio_json import NetioJsonDriver


CredentialResolver = Callable[[str], Mapping[str, Any]]


@dataclass
class RegisteredController:
    definition: PowerController
    driver: PowerDriver
    outlets: Dict[str, PowerOutlet]


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


class PowerRegistry:
    def __init__(self, controllers: Iterable[RegisteredController]) -> None:
        self._controllers = {controller.definition.id: controller for controller in controllers}

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        sleep_fn: Optional[Callable[[float], None]] = None,
        credential_resolver: Optional[CredentialResolver] = None,
    ) -> "PowerRegistry":
        if not isinstance(config, Mapping):
            raise ValidationError("power configuration must be an object")
        raw_controllers = config.get("controllers", [])
        raw_outlets = config.get("outlets", [])
        if not isinstance(raw_controllers, list) or not isinstance(raw_outlets, list):
            raise ValidationError("controllers and outlets must be arrays")

        outlets_by_controller: Dict[str, Dict[str, PowerOutlet]] = {}
        for raw_outlet in raw_outlets:
            if not isinstance(raw_outlet, Mapping):
                raise ValidationError("every power outlet must be an object")
            controller_id = str(raw_outlet.get("controllerId", raw_outlet.get("controller_id")) or "").strip()
            outlet_key = str(raw_outlet.get("outlet", raw_outlet.get("outletKey")) or "").strip()
            outlet = PowerOutlet(
                controller_id=controller_id,
                outlet_key=outlet_key,
                display_name=(str(raw_outlet.get("displayName") or "").strip() or None),
                logical_name=(str(raw_outlet.get("logicalName") or "").strip() or None),
                protected=_bool(raw_outlet.get("protected")),
                default_state=str(raw_outlet.get("defaultState") or "off").strip().lower(),
            )
            controller_outlets = outlets_by_controller.setdefault(controller_id, {})
            if outlet.outlet_key in controller_outlets:
                raise ValidationError(
                    f"duplicate outlet {outlet.outlet_key} for controller {controller_id}"
                )
            controller_outlets[outlet.outlet_key] = outlet

        registered: List[RegisteredController] = []
        seen_ids = set()
        for raw_controller in raw_controllers:
            if not isinstance(raw_controller, Mapping):
                raise ValidationError("every power controller must be an object")
            controller_id = str(raw_controller.get("id") or "")
            controller_name = str(raw_controller.get("name") or controller_id)
            driver_name = str(raw_controller.get("driver") or "")
            definition = PowerController(
                id=controller_id,
                name=controller_name,
                driver_name=driver_name,
                enabled=_bool(raw_controller.get("enabled"), True),
                host=(str(raw_controller.get("host") or "").strip() or None),
                port=raw_controller.get("port"),
                credential_ref=(str(raw_controller.get("credentialRef") or "").strip() or None),
                config=dict(raw_controller.get("config") or {}),
            )
            if definition.id in seen_ids:
                raise ValidationError(f"duplicate controller id: {definition.id}")
            seen_ids.add(definition.id)

            controller_outlets = outlets_by_controller.setdefault(definition.id, {})
            configured_outlets = definition.config.get("outlets", [])
            if configured_outlets and not isinstance(configured_outlets, list):
                raise ValidationError(f"controller {definition.id} config.outlets must be an array")
            for raw_outlet in configured_outlets:
                if isinstance(raw_outlet, Mapping):
                    outlet_key = str(raw_outlet.get("outlet") or raw_outlet.get("id") or "").strip()
                    outlet = PowerOutlet(
                        controller_id=definition.id,
                        outlet_key=outlet_key,
                        display_name=(str(raw_outlet.get("displayName") or "").strip() or None),
                        logical_name=(str(raw_outlet.get("logicalName") or "").strip() or None),
                        protected=_bool(raw_outlet.get("protected")),
                        default_state=str(raw_outlet.get("defaultState") or "off").strip().lower(),
                    )
                else:
                    outlet = PowerOutlet(controller_id=definition.id, outlet_key=str(raw_outlet))
                if not outlet.outlet_key:
                    raise ValidationError(f"controller {definition.id} contains an empty outlet")
                if outlet.outlet_key not in controller_outlets:
                    controller_outlets[outlet.outlet_key] = outlet

            if not controller_outlets and definition.driver_name == "mock":
                raise ValidationError(f"controller {definition.id} requires at least one outlet")
            if definition.driver_name == "mock":
                driver = MockPowerDriver(
                    definition.id,
                    (
                        (outlet_id, outlet.default_state)
                        for outlet_id, outlet in controller_outlets.items()
                    ),
                    sleep_fn=sleep_fn,
                )
            elif definition.driver_name == "apc-powernet-snmp":
                if not definition.host:
                    raise ValidationError(f"controller {definition.id} requires a host")
                if not definition.credential_ref:
                    raise ValidationError(f"controller {definition.id} requires credentialRef")
                if credential_resolver is None:
                    raise ValidationError(
                        f"controller {definition.id} requires a power credential resolver"
                    )
                try:
                    credentials = credential_resolver(definition.credential_ref)
                except Exception as exc:
                    raise ValidationError(
                        f"controller {definition.id} power credentials could not be resolved"
                    ) from exc
                if not isinstance(credentials, Mapping):
                    raise ValidationError(f"controller {definition.id} power credentials are invalid")
                driver = ApcPowerNetSnmpDriver(
                    definition.id,
                    definition.host,
                    port=definition.port or 161,
                    config=definition.config,
                    credentials=credentials,
                )
            elif definition.driver_name == "netio-json":
                if not definition.host:
                    raise ValidationError(f"controller {definition.id} requires a host")
                credentials = {}
                if definition.credential_ref:
                    if credential_resolver is None:
                        raise ValidationError(
                            f"controller {definition.id} requires a power credential resolver"
                        )
                    try:
                        credentials = credential_resolver(definition.credential_ref)
                    except Exception as exc:
                        raise ValidationError(
                            f"controller {definition.id} power credentials could not be resolved"
                        ) from exc
                    if not isinstance(credentials, Mapping):
                        raise ValidationError(f"controller {definition.id} power credentials are invalid")
                use_https = _bool(definition.config.get("useHttps"), False)
                driver = NetioJsonDriver(
                    definition.id,
                    definition.host,
                    port=definition.port or (443 if use_https else 80),
                    config=definition.config,
                    credentials=credentials,
                    sleep_fn=sleep_fn,
                )
            else:
                raise ValidationError(f"unsupported power driver '{definition.driver_name}'")
            registered.append(RegisteredController(definition, driver, controller_outlets))
        return cls(registered)

    def get(self, controller_id: str) -> RegisteredController:
        controller = self._controllers.get(str(controller_id))
        if controller is None:
            raise KeyError(f"controller '{controller_id}' not found")
        return controller

    def all(self) -> List[RegisteredController]:
        return [self._controllers[key] for key in sorted(self._controllers)]

    def get_outlet(self, controller_id: str, outlet_id: str) -> tuple[RegisteredController, PowerOutlet]:
        controller = self.get(controller_id)
        outlet = controller.outlets.get(str(outlet_id))
        if outlet is None:
            try:
                self._refresh_outlets(controller)
            except PowerDriverError:
                pass
            outlet = controller.outlets.get(str(outlet_id))
        if outlet is None:
            raise KeyError(f"outlet '{outlet_id}' not found on controller '{controller_id}'")
        return controller, outlet

    @staticmethod
    def _read_configuration(controller: RegisteredController) -> Dict[str, Any]:
        reader = getattr(controller.driver, "read_configuration", None)
        if callable(reader):
            try:
                configuration = reader()
            except NotImplementedError:
                configuration = None
            if configuration is None:
                return {
                    "writable": False,
                    "fields": [],
                    "outlets": controller.driver.list_outlets(),
                }
            if not isinstance(configuration, Mapping):
                raise PowerDriverError("power driver returned an invalid configuration")
            return dict(configuration)
        return {
            "writable": False,
            "fields": [],
            "outlets": controller.driver.list_outlets(),
        }

    @staticmethod
    def _remote_outlets(configuration: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        outlets = configuration.get("outlets", [])
        if not isinstance(outlets, list):
            raise PowerDriverError("power driver returned an invalid outlet configuration")
        if any(not isinstance(outlet, Mapping) for outlet in outlets):
            raise PowerDriverError("power driver returned an invalid outlet configuration")
        return list(outlets)

    def _refresh_outlets(self, controller: RegisteredController) -> List[Mapping[str, Any]]:
        configuration = self._read_configuration(controller)
        remote_outlets = self._remote_outlets(configuration)
        return self._merge_remote_outlets(controller, remote_outlets)

    @staticmethod
    def _merge_remote_outlets(
        controller: RegisteredController,
        remote_outlets: Iterable[Mapping[str, Any]],
    ) -> List[Mapping[str, Any]]:
        remote_outlets = list(remote_outlets)
        refreshed: Dict[str, PowerOutlet] = {}
        for remote in remote_outlets:
            outlet_id = str(remote.get("outlet") or remote.get("outletKey") or "").strip()
            if not outlet_id:
                raise PowerDriverError("power driver returned an outlet without an ID")
            if outlet_id in refreshed:
                raise PowerDriverError(f"power driver returned duplicate outlet '{outlet_id}'")
            local = controller.outlets.get(outlet_id)
            if local is None:
                local = PowerOutlet(controller.definition.id, outlet_id)
            refreshed[outlet_id] = local
        controller.outlets = refreshed
        return remote_outlets

    @staticmethod
    def _public_metadata(controller: RegisteredController) -> Dict[str, Any]:
        return {
            "id": controller.definition.id,
            "name": controller.definition.name,
            "driver": controller.definition.driver_name,
            "enabled": controller.definition.enabled,
            "host": controller.definition.host,
            "port": controller.definition.port,
            "credentialRef": controller.definition.credential_ref,
            "config": {
                key: controller.definition.config[key]
                for key in (
                    "profile",
                    "snmpVersion",
                    "timeoutSeconds",
                    "retries",
                    "moduleIndex",
                    "path",
                    "useHttps",
                    "verifyTls",
                )
                if key in controller.definition.config
            },
            "capabilities": getattr(
                controller.driver,
                "capabilities",
                PowerCapabilities(),
            ).to_dict(),
        }

    def public_catalog_description(self, controller: RegisteredController) -> Dict[str, Any]:
        """Return local controller configuration without contacting hardware."""
        public = self._public_metadata(controller)
        public["discovery"] = {}
        public["deviceConfiguration"] = {"writable": False, "fields": []}
        public["outlets"] = [
            outlet.to_dict("unknown")
            for _, outlet in sorted(controller.outlets.items())
        ]
        return public

    def public_description(self, controller: RegisteredController) -> Dict[str, Any]:
        """Return local safety metadata enriched with live hardware configuration."""
        configuration: Dict[str, Any] = {}
        try:
            configuration = self._read_configuration(controller)
            remote_outlets = self._remote_outlets(configuration)
            self._merge_remote_outlets(controller, remote_outlets)
        except PowerDriverError:
            remote_outlets = []
        try:
            discovery = controller.driver.discover()
        except PowerDriverError as exc:
            discovery = {
                "reachable": False,
                "errorCode": getattr(exc, "error_code", "DRIVER_ERROR"),
            }
        public = self._public_metadata(controller)
        public["discovery"] = discovery
        public["deviceConfiguration"] = {
            "writable": configuration.get("writable", False) is True,
            "fields": list(configuration.get("fields") or []),
        }
        remote_by_id = {
            str(item.get("outlet") or item.get("outletKey") or "").strip(): item
            for item in remote_outlets
        }
        public["outlets"] = [
            outlet.to_dict(
                remote_by_id.get(outlet_id, {}).get("state", "unknown"),
                remote_by_id.get(outlet_id),
            )
            for outlet_id, outlet in sorted(controller.outlets.items())
        ]
        return public
