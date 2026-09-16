"""Composition adapter for Lab Station host provisioning values."""

from typing import Any, Dict, Optional, Tuple

from host_provisioning_context import HostProvisioningContext
from host_provisioning_values import (
    build_provisioned_host,
    sanitize_host_name,
)


class HostProvisioningRuntime:
    """Expose host provisioning values through explicit dependencies."""

    def __init__(self, context: HostProvisioningContext):
        self._context = context

    def sanitize_host_name(
        self,
        value: Any,
        fallback: Optional[Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        return sanitize_host_name(
            value,
            fallback,
            name_pattern=self._context.get_name_pattern(),
        )

    def build_provisioned_host(
        self,
        payload: Dict[str, Any],
        connection: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        context = self._context
        return build_provisioned_host(
            payload,
            connection,
            sanitize_host_name_fn=context.get_sanitize_host_name,
            normalize_mac_fn=context.normalize_mac,
            normalize_trust_ref_fn=context.normalize_trust_ref,
            default_heartbeat_path=context.default_heartbeat_path,
            default_events_path=context.default_events_path,
        )


def create_host_provisioning_runtime(
    context: HostProvisioningContext,
) -> HostProvisioningRuntime:
    """Create a host provisioning adapter bound to explicit dependencies."""
    return HostProvisioningRuntime(context)


__all__ = ["HostProvisioningRuntime", "create_host_provisioning_runtime"]
