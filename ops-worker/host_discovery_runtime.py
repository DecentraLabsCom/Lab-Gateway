"""Composition adapter for network, heartbeat and Lab Station discovery."""

from typing import Any, Dict, List, Optional, Tuple

from host_discovery_context import HostDiscoveryContext


class HostDiscoveryRuntime:
    """Expose discovery helpers through explicit network and integration ports."""

    def __init__(self, context: HostDiscoveryContext):
        self._context = context

    def is_valid_ping_target(self, target: str) -> bool:
        return self._context.is_valid_ping_target_impl(target)

    def host_is_up(
        self,
        target: str,
        timeout: float,
        probe_port: Optional[int] = None,
    ) -> bool:
        return self._context.host_is_up_impl(
            target,
            timeout,
            probe_port,
            is_valid_target=self._context.get_is_valid_ping_target(),
            winrm_port=self._context.get_winrm_port(),
            create_connection=self._context.get_create_connection(),
            warn=self._context.get_logger().warning,
        )

    def normalize_match_key(self, value: Optional[Any]) -> str:
        return self._context.normalize_match_key_impl(value)

    def tcp_port_open(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
    ) -> bool:
        return self._context.tcp_port_open_impl(
            host,
            port,
            timeout,
            default_timeout=self._context.get_discovery_timeout(),
            create_connection=self._context.get_create_connection(),
        )

    def response_looks_like_labstation(self, response: Any) -> Tuple[bool, Optional[str]]:
        return self._context.response_looks_like_labstation_impl(response)

    def normalize_mac(self, value: Any) -> str:
        return self._context.normalize_mac_impl(
            value,
            mac_pattern=self._context.get_mac_pattern(),
        )

    def parse_boolish(self, value: Any) -> bool:
        return self._context.parse_boolish_impl(value)

    def extract_nic_candidates_from_heartbeat(
        self,
        heartbeat: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._context.extract_nic_candidates_impl(
            heartbeat,
            normalize_mac_fn=self._context.get_normalize_mac(),
            parse_boolish_fn=self._context.get_parse_boolish(),
        )

    def choose_wol_mac(self, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return self._context.choose_wol_mac_impl(candidates)

    def suggest_mac_from_heartbeat(
        self,
        heartbeat: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._context.suggest_mac_from_heartbeat_impl(
            heartbeat,
            normalize_mac_fn=self._context.get_normalize_mac(),
            parse_boolish_fn=self._context.get_parse_boolish(),
        )

    def probe_labstation_http(self, host: str) -> Dict[str, Any]:
        return self._context.probe_labstation_http_impl(
            host,
            ports=self._context.get_discovery_ports(),
            paths=self._context.get_discovery_paths(),
            timeout=self._context.get_discovery_timeout(),
            http_get=self._context.get_http_get(),
            request_exception_type=self._context.get_request_exception(),
            response_classifier=self._context.get_response_classifier(),
            suggest_mac=self._context.get_suggest_mac(),
        )

    def query_labstation_task_heartbeat_path(
        self,
        host: Dict[str, Any],
    ) -> Optional[str]:
        return self._context.query_labstation_task_heartbeat_path_impl(
            host,
            run_remote_powershell=self._context.get_run_remote_powershell(),
            parse_json=self._context.get_json_loads(),
            logger=self._context.get_logger(),
        )

    def build_heartbeat_path_candidates(self, host: Dict[str, Any]) -> List[str]:
        return self._context.build_heartbeat_path_candidates_impl(
            host,
            query_task_path=self._context.get_query_task_path(),
            configured_paths=self._context.get_heartbeat_paths(),
        )

    def discover_heartbeat_hint(self, hostname: str) -> Dict[str, Any]:
        return self._context.discover_heartbeat_hint_impl(
            hostname,
            credentials_configured=self._context.get_credentials_configured(),
            path_candidates=self._context.get_path_candidates(),
            read_remote_file=self._context.get_read_remote_file(),
            parse_json=self._context.get_json_loads(),
            suggest_mac=self._context.get_suggested_mac(),
            winrm_port=self._context.get_winrm_port(),
            logger=self._context.get_logger(),
        )

    def guacamole_name_candidates(self, connection: Dict[str, Any]) -> List[str]:
        return self._context.guacamole_name_candidates_impl(
            connection,
            load_connections=self._context.get_load_guacamole_connections(),
            normalize_key=self._context.get_normalize_match_key(),
        )

    def resolve_guacamole_connection(self, connection_id: Any) -> Optional[Dict[str, Any]]:
        return self._context.resolve_guacamole_connection_impl(
            connection_id,
            load_connections=self._context.get_load_guacamole_connections(),
        )

    def discover_labstation_candidate(self, connection: Dict[str, Any]) -> Dict[str, Any]:
        return self._context.discover_labstation_candidate_impl(
            connection,
            normalize_host=self._context.get_normalize_match_key(),
            resolve_dns=self._context.get_resolve_dns(),
            tcp_probe=self._context.get_tcp_probe(),
            http_probe=self._context.get_http_probe(),
            heartbeat_hint=self._context.get_heartbeat_hint(),
            name_candidates=self._context.get_name_candidates(),
            winrm_port=self._context.get_winrm_port(),
            discovery_timeout=self._context.get_discovery_timeout(),
            heartbeat_paths=self._context.get_heartbeat_paths(),
            draft_winrm_port=5986,
            events_path=self._context.get_events_path(),
        )


def create_host_discovery_runtime(context: HostDiscoveryContext) -> HostDiscoveryRuntime:
    """Create a discovery adapter bound to explicit ports."""
    return HostDiscoveryRuntime(context)


__all__ = ["HostDiscoveryRuntime", "create_host_discovery_runtime"]
