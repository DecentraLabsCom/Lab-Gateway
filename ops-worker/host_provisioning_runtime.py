"""Composition adapter for Lab Station host provisioning values."""

from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple


class HostProvisioningRuntime:
    """Resolve host naming and provisioning helpers from live worker providers."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def sanitize_host_name(
        self,
        value: Any,
        fallback: Optional[Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        return self._get("_sanitize_host_name_impl")(
            value,
            fallback,
            name_pattern=self._get("HOST_NAME_RE"),
        )

    def normalize_labs(self, value: Any) -> List[str]:
        return self._get("_normalize_labs_impl")(value)

    def validate_labs_against_candidates(
        self,
        labs: List[str],
        candidates: Any,
    ) -> Optional[str]:
        return self._get("_validate_labs_against_candidates_impl")(labs, candidates)

    def build_provisioned_host(
        self,
        payload: Dict[str, Any],
        connection: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        get = self._get
        return get("_build_provisioned_host_impl")(
            payload,
            connection,
            sanitize_host_name_fn=get("sanitize_host_name"),
            normalize_labs_fn=get("normalize_labs"),
            validate_labs_fn=get("validate_labs_against_candidates"),
            normalize_mac_fn=get("normalize_mac"),
            normalize_trust_ref_fn=get("normalize_winrm_trust_ref"),
            default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
            default_events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        )


def create_host_provisioning_runtime(
    providers: Mapping[str, Any],
) -> HostProvisioningRuntime:
    """Create a host provisioning adapter bound to live providers."""
    return HostProvisioningRuntime(providers)


__all__ = ["HostProvisioningRuntime", "create_host_provisioning_runtime"]
