"""Composition adapter for the Ops Worker host catalog and database inputs."""

from typing import Any, Dict, List, Optional, Tuple

from host_config_context import HostConfigContext


class HostConfigRuntime:
    """Expose catalog/configuration operations through explicit dependency ports."""

    def __init__(self, context: HostConfigContext):
        self._context = context

    def read_hosts_config(self, path: str, missing_ok: bool = True) -> Dict[str, Any]:
        return self._context.read_hosts_config_impl(path, missing_ok)

    def merge_host_configs(
        self,
        base: Dict[str, Any],
        dynamic: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._context.merge_host_configs_impl(base, dynamic)

    def resolve_host_secret_refs(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return self._context.resolve_host_secret_refs_impl(
            raw,
            credential_ref_for_host=self._context.get_credential_ref_for_host(),
            credentials_configured=self._context.get_credentials_configured(),
            warn=self._context.get_logger().warning,
        )

    def catalog_bool(self, value: Any) -> bool:
        return self._context.catalog_bool_impl(value)

    def resolved_addresses(self, address: str) -> List[Any]:
        return self._context.resolve_addresses_impl(
            address,
            ip_address=self._context.get_ip_address(),
            getaddrinfo=self._context.get_getaddrinfo(),
        )

    def validate_winrm_catalog(self, config: Dict[str, Any]) -> None:
        return self._context.validate_winrm_catalog_impl(
            config,
            management_cidrs=self._context.get_management_cidrs(),
            winrm_port=self._context.get_winrm_port(),
            catalog_bool=self._context.get_catalog_bool(),
            resolve_addresses=self._context.get_resolved_addresses(),
            trust_ref_pattern=self._context.get_trust_ref_pattern(),
        )

    def load_config(self) -> Dict[str, Any]:
        return self._context.load_host_config_impl(
            self._context.get_config_path(),
            self._context.get_dynamic_config_path(),
            read_config=self._context.get_read_hosts_config(),
            merge_configs=self._context.get_merge_host_configs(),
            validate_config=self._context.get_validate_winrm_catalog(),
            resolve_secret_refs=self._context.get_resolve_host_secret_refs(),
        )

    def build_ops_dsn(self) -> Optional[str]:
        return self._context.build_ops_dsn_impl(
            self._context.get_mysql_dsn(),
            self._context.get_ops_mysql_user(),
            self._context.get_ops_mysql_password(),
            self._context.get_ops_mysql_database(),
            self._context.get_mysql_hostname(),
            self._context.get_mysql_port(),
            create_url=self._context.get_url_create(),
        )

    def build_guacamole_dsn(self) -> Optional[str]:
        return self._context.build_guacamole_dsn_impl(
            self._context.get_guacamole_dsn(),
            self._context.get_guacamole_user(),
            self._context.get_guacamole_password(),
            self._context.get_guacamole_database(),
            self._context.get_mysql_dsn(),
            self._context.get_mysql_hostname(),
            self._context.get_mysql_port(),
            create_url=self._context.get_url_create(),
            parse_url=self._context.get_parse_url(),
            logger=self._context.get_logger(),
        )

    def load_dynamic_config(self) -> Dict[str, Any]:
        return self._context.load_dynamic_config_impl(
            self._context.get_dynamic_config_path(),
            read_config=self._context.get_read_hosts_config(),
        )

    def write_dynamic_config(self, config: Dict[str, Any]) -> None:
        return self._context.write_dynamic_config_impl(
            config,
            self._context.get_dynamic_config_path(),
            path_dirname=self._context.get_path_dirname(),
            make_dirs=self._context.get_make_dirs(),
            open_file=self._context.get_open_file(),
            dump_json=self._context.get_dump_json(),
            replace_file=self._context.get_replace_file(),
        )

    def upsert_dynamic_host(self, host_config: Dict[str, Any]) -> None:
        return self._context.upsert_dynamic_host_impl(
            host_config,
            load_config=self._context.get_load_dynamic_config(),
            write_config=self._context.get_write_dynamic_config(),
        )

    def update_dynamic_host(
        self,
        host_name: str,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return self._context.update_dynamic_host_impl(
            host_name,
            payload,
            load_config=self._context.get_load_dynamic_config(),
            write_config=self._context.get_write_dynamic_config(),
            normalize_key=self._context.get_normalize_match_key(),
            sanitize_name=self._context.get_sanitize_host_name(),
            normalize_mac=self._context.get_normalize_mac(),
            host_get=self._context.get_host_get(),
        )


def create_host_config_runtime(context: HostConfigContext) -> HostConfigRuntime:
    """Create a host/config adapter bound to explicit ports."""
    return HostConfigRuntime(context)


__all__ = ["HostConfigRuntime", "create_host_config_runtime"]
