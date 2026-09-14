"""Composition adapter for network, heartbeat and Lab Station discovery."""

from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple


class HostDiscoveryRuntime:
    """Resolve discovery helpers from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def is_valid_ping_target(self, target: str) -> bool:
        return self._get("_is_valid_ping_target_impl")(target)

    def host_is_up(
        self,
        target: str,
        timeout: float,
        probe_port: Optional[int] = None,
    ) -> bool:
        get = self._get
        target_validator = self._providers.get("_is_valid_ping_target")
        if target_validator is None:
            target_validator = self._providers.get("is_valid_ping_target")
        if target_validator is None:
            target_validator = get("_is_valid_ping_target_impl")
        return get("_host_is_up_impl")(
            target,
            timeout,
            probe_port,
            is_valid_target=target_validator,
            winrm_port=get("WINRM_PORT"),
            create_connection=get("socket").create_connection,
            warn=get("logging").warning,
        )

    def normalize_match_key(self, value: Optional[Any]) -> str:
        return self._get("_normalize_match_key_impl")(value)

    def tcp_port_open(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
    ) -> bool:
        get = self._get
        return get("_tcp_port_open_impl")(
            host,
            port,
            timeout,
            default_timeout=get("DISCOVERY_TIMEOUT_SECONDS"),
            create_connection=get("socket").create_connection,
        )

    def response_looks_like_labstation(self, response: Any) -> Tuple[bool, Optional[str]]:
        return self._get("_response_looks_like_labstation_impl")(response)

    def normalize_mac(self, value: Any) -> str:
        return self._get("_normalize_mac_impl")(
            value,
            mac_pattern=self._get("MAC_RE"),
        )

    def parse_boolish(self, value: Any) -> bool:
        return self._get("_parse_boolish_impl")(value)

    def extract_nic_candidates_from_heartbeat(
        self,
        heartbeat: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        get = self._get
        return get("_extract_nic_candidates_from_heartbeat_impl")(
            heartbeat,
            normalize_mac_fn=get("normalize_mac"),
            parse_boolish_fn=get("parse_boolish"),
        )

    def choose_wol_mac(self, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return self._get("_choose_wol_mac_impl")(candidates)

    def suggest_mac_from_heartbeat(
        self,
        heartbeat: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        get = self._get
        return get("_suggest_mac_from_heartbeat_impl")(
            heartbeat,
            normalize_mac_fn=get("normalize_mac"),
            parse_boolish_fn=get("parse_boolish"),
        )

    def probe_labstation_http(self, host: str) -> Dict[str, Any]:
        get = self._get
        requests = get("requests")
        return get("_probe_labstation_http_impl")(
            host,
            ports=get("DISCOVERY_LABSTATION_PORTS"),
            paths=get("DISCOVERY_LABSTATION_PATHS"),
            timeout=get("DISCOVERY_TIMEOUT_SECONDS"),
            http_get=requests.get,
            request_exception_type=requests.RequestException,
            response_classifier=get("response_looks_like_labstation"),
            suggest_mac=get("suggest_mac_from_heartbeat"),
        )

    def query_labstation_task_heartbeat_path(
        self,
        host: Dict[str, Any],
    ) -> Optional[str]:
        get = self._get
        return get("_query_labstation_task_heartbeat_path_impl")(
            host,
            run_remote_powershell=get("run_remote_powershell"),
            parse_json=get("json").loads,
            logger=get("logging"),
        )

    def build_heartbeat_path_candidates(self, host: Dict[str, Any]) -> List[str]:
        get = self._get
        return get("_build_heartbeat_path_candidates_impl")(
            host,
            query_task_path=get("query_labstation_task_heartbeat_path"),
            configured_paths=get("DISCOVERY_HEARTBEAT_PATHS"),
        )

    def discover_heartbeat_hint(self, hostname: str) -> Dict[str, Any]:
        get = self._get
        return get("_discover_heartbeat_hint_impl")(
            hostname,
            credentials_configured=get("winrm_credentials_configured"),
            path_candidates=get("build_heartbeat_path_candidates"),
            read_remote_file=get("read_remote_file"),
            parse_json=get("json").loads,
            suggest_mac=get("suggest_mac_from_heartbeat"),
            winrm_port=get("WINRM_PORT"),
            logger=get("logging"),
        )

    def guacamole_name_candidates(self, connection: Dict[str, Any]) -> List[str]:
        get = self._get
        return get("_guacamole_name_candidates_impl")(
            connection,
            load_connections=get("load_guacamole_connections"),
            normalize_key=get("normalize_match_key"),
        )

    def resolve_guacamole_connection(self, connection_id: Any) -> Optional[Dict[str, Any]]:
        get = self._get
        return get("_resolve_guacamole_connection_impl")(
            connection_id,
            load_connections=get("load_guacamole_connections"),
        )

    def discover_labstation_candidate(self, connection: Dict[str, Any]) -> Dict[str, Any]:
        get = self._get
        return get("_discover_labstation_candidate_impl")(
            connection,
            normalize_host=get("normalize_match_key"),
            resolve_dns=get("socket").getaddrinfo,
            tcp_probe=get("tcp_port_open"),
            http_probe=get("probe_labstation_http"),
            heartbeat_hint=get("discover_heartbeat_hint"),
            name_candidates=get("guacamole_name_candidates"),
            winrm_port=get("WINRM_PORT"),
            discovery_timeout=get("DISCOVERY_TIMEOUT_SECONDS"),
            heartbeat_paths=get("DISCOVERY_HEARTBEAT_PATHS"),
            draft_winrm_port=5986,
            events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        )


def create_host_discovery_runtime(providers: Mapping[str, Any]) -> HostDiscoveryRuntime:
    """Create a discovery adapter bound to live providers."""
    return HostDiscoveryRuntime(providers)


__all__ = ["HostDiscoveryRuntime", "create_host_discovery_runtime"]
