"""Explicit dependencies for Ops Worker host catalog configuration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class HostConfigContext:
    """Catalog, dynamic-file and DSN ports used by the configuration runtime."""

    read_hosts_config_impl: Callable[..., Dict[str, Any]]
    merge_host_configs_impl: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    resolve_host_secret_refs_impl: Callable[..., Dict[str, Any]]
    get_credential_ref_for_host: Callable[[], Callable[..., str]]
    get_credentials_configured: Callable[[], Callable[[str], bool]]
    get_logger: Callable[[], Any]
    catalog_bool_impl: Callable[[Any], bool]
    resolve_addresses_impl: Callable[..., List[Any]]
    get_ip_address: Callable[[], Callable[..., Any]]
    get_getaddrinfo: Callable[[], Callable[..., Any]]
    validate_winrm_catalog_impl: Callable[..., None]
    get_management_cidrs: Callable[[], List[str]]
    get_winrm_port: Callable[[], int]
    get_trust_ref_pattern: Callable[[], Any]
    get_catalog_bool: Callable[[], Callable[[Any], bool]]
    get_resolved_addresses: Callable[[], Callable[[str], List[Any]]]
    load_host_config_impl: Callable[..., Dict[str, Any]]
    get_config_path: Callable[[], str]
    get_dynamic_config_path: Callable[[], str]
    get_read_hosts_config: Callable[[], Callable[..., Dict[str, Any]]]
    get_merge_host_configs: Callable[[], Callable[..., Dict[str, Any]]]
    get_validate_winrm_catalog: Callable[[], Callable[..., None]]
    get_resolve_host_secret_refs: Callable[[], Callable[..., Dict[str, Any]]]
    build_ops_dsn_impl: Callable[..., Optional[str]]
    get_mysql_dsn: Callable[[], Optional[str]]
    get_ops_mysql_user: Callable[[], str]
    get_ops_mysql_password: Callable[[], str]
    get_ops_mysql_database: Callable[[], Optional[str]]
    get_mysql_hostname: Callable[[], str]
    get_mysql_port: Callable[[], int]
    get_url_create: Callable[[], Callable[..., Any]]
    build_guacamole_dsn_impl: Callable[..., Optional[str]]
    get_guacamole_dsn: Callable[[], Optional[str]]
    get_guacamole_user: Callable[[], str]
    get_guacamole_password: Callable[[], str]
    get_guacamole_database: Callable[[], Optional[str]]
    get_parse_url: Callable[[], Callable[[str], Any]]
    get_load_dynamic_config: Callable[[], Callable[[], Dict[str, Any]]]
    get_write_dynamic_config: Callable[[], Callable[[Dict[str, Any]], None]]
    load_dynamic_config_impl: Callable[..., Dict[str, Any]]
    write_dynamic_config_impl: Callable[..., None]
    get_path_dirname: Callable[[], Callable[[str], str]]
    get_make_dirs: Callable[[], Callable[..., Any]]
    get_open_file: Callable[[], Callable[..., Any]]
    get_dump_json: Callable[[], Callable[..., Any]]
    get_replace_file: Callable[[], Callable[[str, str], Any]]
    upsert_dynamic_host_impl: Callable[..., None]
    get_normalize_match_key: Callable[[], Callable[[Any], str]]
    get_sanitize_host_name: Callable[[], Callable[..., Any]]
    get_normalize_mac: Callable[[], Callable[[Any], Optional[str]]]
    get_host_get: Callable[[], Callable[[str], Optional[Dict[str, Any]]]]
    update_dynamic_host_impl: Callable[..., Any]


__all__ = ["HostConfigContext"]
