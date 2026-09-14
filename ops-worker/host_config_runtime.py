"""Composition adapter for the Ops Worker host catalog and database inputs."""

import builtins

from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple


class HostConfigRuntime:
    """Resolve catalog/configuration operations from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def read_hosts_config(self, path: str, missing_ok: bool = True) -> Dict[str, Any]:
        return self._get("_read_hosts_config_impl")(path, missing_ok)

    def merge_host_configs(
        self,
        base: Dict[str, Any],
        dynamic: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._get("_merge_host_configs_impl")(base, dynamic)

    def resolve_host_secret_refs(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        get = self._get
        return get("_resolve_host_secret_refs_impl")(
            raw,
            credential_ref_for_host=get("credential_ref_for_host"),
            credentials_configured=get("winrm_credentials_configured"),
            warn=get("logging").warning,
        )

    def catalog_bool(self, value: Any) -> bool:
        return self._get("_catalog_bool_impl")(value)

    def resolved_addresses(self, address: str) -> List[Any]:
        get = self._get
        return get("_resolve_addresses_impl")(
            address,
            ip_address=get("ipaddress").ip_address,
            getaddrinfo=get("socket").getaddrinfo,
        )

    def validate_winrm_catalog(self, config: Dict[str, Any]) -> None:
        get = self._get
        return get("_validate_winrm_catalog_impl")(
            config,
            management_cidrs=get("WINRM_MANAGEMENT_CIDRS"),
            winrm_port=get("WINRM_PORT"),
            catalog_bool=get("_catalog_bool"),
            resolve_addresses=get("_resolved_addresses"),
            trust_ref_pattern=get("WINRM_TRUST_REF_RE"),
        )

    def load_config(self) -> Dict[str, Any]:
        get = self._get
        return get("_load_host_config_impl")(
            get("CONFIG_PATH"),
            get("DYNAMIC_CONFIG_PATH"),
            read_config=get("read_hosts_config"),
            merge_configs=get("merge_host_configs"),
            validate_config=get("validate_winrm_catalog"),
            resolve_secret_refs=get("resolve_host_secret_refs"),
        )

    def build_ops_dsn(self) -> Optional[str]:
        get = self._get
        return get("_build_ops_dsn_impl")(
            get("MYSQL_DSN"),
            get("OPS_MYSQL_USER"),
            get("OPS_MYSQL_PASSWORD"),
            get("OPS_MYSQL_DATABASE"),
            get("MYSQL_HOSTNAME"),
            get("MYSQL_PORT"),
            create_url=get("URL").create,
        )

    def build_guacamole_dsn(self) -> Optional[str]:
        get = self._get
        return get("_build_guacamole_dsn_impl")(
            get("GUACAMOLE_MYSQL_DSN"),
            get("GUACAMOLE_MYSQL_USER"),
            get("GUACAMOLE_MYSQL_PASSWORD"),
            get("GUACAMOLE_MYSQL_DATABASE"),
            get("MYSQL_DSN"),
            get("MYSQL_HOSTNAME"),
            get("MYSQL_PORT"),
            create_url=get("URL").create,
            parse_url=get("make_url"),
            logger=get("logging"),
        )

    def load_dynamic_config(self) -> Dict[str, Any]:
        get = self._get
        return get("_load_dynamic_config_impl")(
            get("DYNAMIC_CONFIG_PATH"),
            read_config=get("read_hosts_config"),
        )

    def write_dynamic_config(self, config: Dict[str, Any]) -> None:
        get = self._get
        return get("_write_dynamic_config_impl")(
            config,
            get("DYNAMIC_CONFIG_PATH"),
            path_dirname=get("os").path.dirname,
            make_dirs=get("os").makedirs,
            open_file=self._providers.get("open", builtins.open),
            dump_json=get("json").dump,
            replace_file=get("os").replace,
        )

    def upsert_dynamic_host(self, host_config: Dict[str, Any]) -> None:
        get = self._get
        return get("_upsert_dynamic_host_impl")(
            host_config,
            load_config=get("load_dynamic_config"),
            write_config=get("write_dynamic_config"),
        )

    def update_dynamic_host(
        self,
        host_name: str,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        get = self._get
        return get("_update_dynamic_host_impl")(
            host_name,
            payload,
            load_config=get("load_dynamic_config"),
            write_config=get("write_dynamic_config"),
            normalize_key=get("normalize_match_key"),
            sanitize_name=get("sanitize_host_name"),
            normalize_mac=get("normalize_mac"),
            host_get=get("HOSTS").get,
        )


def create_host_config_runtime(providers: Mapping[str, Any]) -> HostConfigRuntime:
    """Create a host/config adapter bound to live providers."""
    return HostConfigRuntime(providers)


__all__ = ["HostConfigRuntime", "create_host_config_runtime"]
