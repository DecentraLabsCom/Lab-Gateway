"""Explicit dependencies for host and Lab Station discovery."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class HostDiscoveryContext:
    """Network, heartbeat and Guacamole ports used by discovery operations."""

    is_valid_ping_target_impl: Callable[[str], bool]
    get_is_valid_ping_target: Callable[[], Callable[[str], bool]]
    host_is_up_impl: Callable[..., bool]
    get_winrm_port: Callable[[], int]
    get_create_connection: Callable[[], Callable[..., Any]]
    get_logger: Callable[[], Any]
    normalize_match_key_impl: Callable[[Optional[Any]], str]
    tcp_port_open_impl: Callable[..., bool]
    get_discovery_timeout: Callable[[], float]
    response_looks_like_labstation_impl: Callable[[Any], Tuple[bool, Optional[str]]]
    normalize_mac_impl: Callable[..., str]
    get_mac_pattern: Callable[[], Any]
    parse_boolish_impl: Callable[[Any], bool]
    extract_nic_candidates_impl: Callable[..., List[Dict[str, Any]]]
    get_normalize_mac: Callable[[], Callable[[Any], str]]
    get_parse_boolish: Callable[[], Callable[[Any], bool]]
    choose_wol_mac_impl: Callable[[List[Dict[str, Any]]], Optional[Dict[str, Any]]]
    suggest_mac_from_heartbeat_impl: Callable[..., Optional[Dict[str, Any]]]
    get_discovery_ports: Callable[[], List[int]]
    get_discovery_paths: Callable[[], List[str]]
    get_http_get: Callable[[], Callable[..., Any]]
    get_request_exception: Callable[[], Any]
    get_response_classifier: Callable[[], Callable[[Any], Tuple[bool, Optional[str]]]]
    get_suggest_mac: Callable[[], Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]]
    probe_labstation_http_impl: Callable[..., Dict[str, Any]]
    query_labstation_task_heartbeat_path_impl: Callable[..., Optional[str]]
    get_run_remote_powershell: Callable[[], Callable[..., Any]]
    get_json_loads: Callable[[], Callable[[str], Any]]
    build_heartbeat_path_candidates_impl: Callable[..., List[str]]
    get_query_task_path: Callable[[], Callable[[Dict[str, Any]], Optional[str]]]
    get_heartbeat_paths: Callable[[], List[str]]
    discover_heartbeat_hint_impl: Callable[..., Dict[str, Any]]
    get_credentials_configured: Callable[[], Callable[[str], bool]]
    get_path_candidates: Callable[[], Callable[[Dict[str, Any]], List[str]]]
    get_read_remote_file: Callable[[], Callable[..., Any]]
    get_suggested_mac: Callable[[], Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]]
    guacamole_name_candidates_impl: Callable[..., List[str]]
    get_load_guacamole_connections: Callable[[], Callable[[], Any]]
    get_normalize_match_key: Callable[[], Callable[[Optional[Any]], str]]
    resolve_guacamole_connection_impl: Callable[..., Optional[Dict[str, Any]]]
    discover_labstation_candidate_impl: Callable[..., Dict[str, Any]]
    get_resolve_dns: Callable[[], Callable[..., Any]]
    get_tcp_probe: Callable[[], Callable[..., bool]]
    get_http_probe: Callable[[], Callable[[str], Dict[str, Any]]]
    get_heartbeat_hint: Callable[[], Callable[[str], Dict[str, Any]]]
    get_name_candidates: Callable[[], Callable[[Dict[str, Any]], List[str]]]
    get_events_path: Callable[[], str]


__all__ = ["HostDiscoveryContext"]
