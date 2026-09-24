"""Composition runtime for the common lab catalog resolver."""

from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from lab_catalog_client import fetch_lab_catalog
from lab_resolution_context import LabResolutionContext
from lab_resolution_service import (
    extract_lab_catalog,
    resolve_lab_associations,
    resolve_host_for_lab,
    resolve_lab_access_key,
    resolve_lab_ids_for_host,
    resolve_lab_resources,
    resolve_lab_status_targets,
)


class LabResolutionRuntime:
    """Cache the provider catalog and expose all lab/host resolution ports."""

    def __init__(self, context: LabResolutionContext):
        self._context = context
        self._catalog: Optional[List[Dict[str, Any]]] = None
        self._catalog_loaded_at = 0.0

    def _load_catalog(self) -> List[Dict[str, Any]]:
        context = self._context
        url = str(context.get_catalog_url() or "").strip()
        if not url:
            return []
        now = context.get_monotonic()()
        with context.get_cache_lock():
            ttl = max(0.0, float(context.get_catalog_cache_seconds()))
            if self._catalog is not None and now - self._catalog_loaded_at < ttl:
                return list(self._catalog)
            try:
                catalog = fetch_lab_catalog(
                    url,
                    context.get_catalog_token(),
                    context.get_catalog_token_header(),
                    allow_insecure=context.get_catalog_allow_insecure(),
                    http_get=context.get_http_get(),
                    timeout=context.get_catalog_timeout(),
                )
            except Exception as exc:  # pylint: disable=broad-except
                context.get_logger().warning(
                    "Unable to load blockchain-services lab catalog: %s",
                    type(exc).__name__,
                )
                self._catalog = []
            else:
                self._catalog = extract_lab_catalog(catalog)
            self._catalog_loaded_at = now
            return list(self._catalog or [])

    def refresh_catalog(self) -> List[Dict[str, Any]]:
        """Force the next resolver operation to load a fresh catalog."""
        with self._context.get_cache_lock():
            self._catalog = None
            self._catalog_loaded_at = 0.0
        return self._load_catalog()

    def resolve_lab_access_key(self, lab_id: Any) -> Optional[str]:
        return resolve_lab_access_key(self._load_catalog(), lab_id)

    def resolve_host_by_lab(self, lab_id: Any) -> Optional[Dict[str, Any]]:
        context = self._context
        labs = self._load_catalog()
        if not labs:
            return None
        connections, _error = context.get_guacamole_connections()
        with context.get_cache_lock():
            hosts = context.get_host_registry().all_hosts()
        return resolve_host_for_lab(
            labs,
            lab_id,
            connections,
            hosts,
            parse_selector=context.get_parse_selector(),
            normalize_key=context.get_normalize_key(),
        )

    def resolve_lab_ids_for_host(self, host: Mapping[str, Any]) -> List[str]:
        context = self._context
        labs = self._load_catalog()
        if not labs:
            return []
        connections, _error = context.get_guacamole_connections()
        with context.get_cache_lock():
            hosts = context.get_host_registry().all_hosts()
        return resolve_lab_ids_for_host(
            labs,
            dict(host),
            connections,
            hosts,
            parse_selector=context.get_parse_selector(),
            normalize_key=context.get_normalize_key(),
        )

    def resolve_lab_associations(self) -> List[Dict[str, str]]:
        """Return the current provider-lab associations to registered hosts."""
        context = self._context
        labs = self._load_catalog()
        if not labs:
            return []
        connections, _error = context.get_guacamole_connections()
        with context.get_cache_lock():
            hosts = context.get_host_registry().all_hosts()
        return resolve_lab_associations(
            labs,
            connections,
            hosts,
            parse_selector=context.get_parse_selector(),
            normalize_key=context.get_normalize_key(),
        )

    def resolve_lab_status_targets(self) -> List[Dict[str, Any]]:
        """Return trusted Guacamole probe targets for every catalog lab."""
        context = self._context
        labs = self._load_catalog()
        if not labs:
            return []
        connections, _error = context.get_guacamole_connections()
        with context.get_cache_lock():
            hosts = context.get_host_registry().all_hosts()
        return resolve_lab_status_targets(
            labs,
            connections,
            hosts,
            parse_selector=context.get_parse_selector(),
            normalize_key=context.get_normalize_key(),
        )

    def resolve_lab_resources(self, *, default_fmu_backend: str = "station") -> List[Dict[str, str]]:
        """Return the catalog resource type for every known laboratory."""
        return resolve_lab_resources(
            self._load_catalog(),
            default_fmu_backend=default_fmu_backend,
        )


def create_lab_resolution_runtime(context: LabResolutionContext) -> LabResolutionRuntime:
    """Create a resolver runtime bound to explicit dependency ports."""
    return LabResolutionRuntime(context)


__all__ = ["LabResolutionRuntime", "create_lab_resolution_runtime"]
