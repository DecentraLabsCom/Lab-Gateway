from types import SimpleNamespace

from host_discovery_runtime import HostDiscoveryRuntime, create_host_discovery_runtime
from host_discovery_service import discover_labstation_candidate


def test_host_discovery_runtime_forwards_network_and_heartbeat_dependencies():
    calls = []
    providers = {
        "_normalize_match_key_impl": lambda value: calls.append(("key", value)) or "host",
        "_tcp_port_open_impl": lambda host, port, timeout, **kwargs: calls.append(
            ("tcp", host, port, timeout, kwargs)
        ) or True,
        "DISCOVERY_TIMEOUT_SECONDS": 1.5,
        "socket": SimpleNamespace(create_connection="connect", getaddrinfo="resolve"),
        "_response_looks_like_labstation_impl": lambda response: (True, "LabStation"),
        "_normalize_mac_impl": lambda value, **kwargs: calls.append(("mac", value, kwargs)) or "AA:BB",
        "MAC_RE": "mac-pattern",
        "normalize_mac": lambda value: "AA:BB",
        "_parse_boolish_impl": lambda value: bool(value),
        "parse_boolish": bool,
        "_extract_nic_candidates_from_heartbeat_impl": lambda heartbeat, **kwargs: calls.append(
            ("nics", heartbeat, kwargs)
        ) or [{"mac": "AA:BB"}],
        "_choose_wol_mac_impl": lambda candidates: calls.append(("choose", candidates)) or candidates[0],
        "_suggest_mac_from_heartbeat_impl": lambda heartbeat, **kwargs: calls.append(
            ("suggest", heartbeat, kwargs)
        ) or {"mac": "AA:BB"},
        "_probe_labstation_http_impl": lambda host, **kwargs: calls.append(
            ("probe", host, kwargs)
        ) or {"detected": True},
        "DISCOVERY_LABSTATION_PORTS": [8765],
        "DISCOVERY_LABSTATION_PATHS": ["/health"],
        "requests": SimpleNamespace(get="get", RequestException=RuntimeError),
        "response_looks_like_labstation": lambda response: (True, "LabStation"),
        "suggest_mac_from_heartbeat": lambda heartbeat: {"mac": "AA:BB"},
        "_query_labstation_task_heartbeat_path_impl": lambda host, **kwargs: calls.append(
            ("task-path", host, kwargs)
        ) or "C:\\heartbeat.json",
        "run_remote_powershell": "powershell",
        "json": SimpleNamespace(loads="loads"),
        "logging": SimpleNamespace(debug=lambda *args: None),
        "_build_heartbeat_path_candidates_impl": lambda host, **kwargs: calls.append(
            ("paths", host, kwargs)
        ) or ["C:\\heartbeat.json"],
        "query_labstation_task_heartbeat_path": lambda host: "C:\\heartbeat.json",
        "DISCOVERY_HEARTBEAT_PATHS": ["C:\\fallback.json"],
        "_discover_heartbeat_hint_impl": lambda hostname, **kwargs: calls.append(
            ("hint", hostname, kwargs)
        ) or {"detected": True},
        "winrm_credentials_configured": lambda hostname: True,
        "build_heartbeat_path_candidates": lambda host: ["C:\\heartbeat.json"],
        "read_remote_file": "read",
        "WINRM_PORT": 5986,
        "suggest_mac_from_heartbeat": lambda heartbeat: {"mac": "AA:BB"},
    }
    runtime = create_host_discovery_runtime(providers)

    assert isinstance(runtime, HostDiscoveryRuntime)
    assert runtime.normalize_match_key(" Host ") == "host"
    assert runtime.tcp_port_open("host", 5986) is True
    assert runtime.normalize_mac("raw") == "AA:BB"
    assert runtime.extract_nic_candidates_from_heartbeat({"status": {}}) == [{"mac": "AA:BB"}]
    assert runtime.choose_wol_mac([{"mac": "AA:BB"}]) == {"mac": "AA:BB"}
    assert runtime.suggest_mac_from_heartbeat({"status": {}}) == {"mac": "AA:BB"}
    assert runtime.probe_labstation_http("host") == {"detected": True}
    assert runtime.query_labstation_task_heartbeat_path({"name": "host"}) == "C:\\heartbeat.json"
    assert runtime.build_heartbeat_path_candidates({"name": "host"}) == ["C:\\heartbeat.json"]
    assert runtime.discover_heartbeat_hint("host") == {"detected": True}
    assert any(call[0] == "hint" for call in calls)


def test_host_discovery_runtime_keeps_guacamole_discovery_callbacks_dynamic():
    calls = []
    providers = {
        "_guacamole_name_candidates_impl": lambda connection, **kwargs: kwargs[
            "load_connections"
        ]()[0],
        "load_guacamole_connections": lambda: ([{"name": "first"}], None),
        "normalize_match_key": lambda value: str(value or "").strip().lower(),
        "_resolve_guacamole_connection_impl": lambda connection_id, **kwargs: kwargs[
            "load_connections"
        ]()[0][0],
        "_discover_labstation_candidate_impl": discover_labstation_candidate,
        "socket": SimpleNamespace(getaddrinfo=lambda *args, **kwargs: []),
        "tcp_port_open": lambda *args, **kwargs: True,
        "probe_labstation_http": lambda host: {"detected": True},
        "discover_heartbeat_hint": lambda host: {"detected": True, "path": "heartbeat.json"},
        "guacamole_name_candidates": lambda connection: ["first"],
        "WINRM_PORT": 5986,
        "DISCOVERY_TIMEOUT_SECONDS": 1.5,
        "DISCOVERY_HEARTBEAT_PATHS": ["fallback.json"],
    }
    runtime = create_host_discovery_runtime(providers)

    assert runtime.guacamole_name_candidates({"hostname": "station"}) == [{"name": "first"}]
    assert runtime.resolve_guacamole_connection(7) == {"name": "first"}
    result = runtime.discover_labstation_candidate({"hostname": "station"})
    assert result["status"] == "labstation-detected"
    assert result["opsHostDraft"]["nameCandidates"] == ["first"]

    providers["load_guacamole_connections"] = lambda: ([{"name": "second"}], None)
    assert runtime.guacamole_name_candidates({"hostname": "station"}) == [{"name": "second"}]


def test_host_discovery_runtime_forwards_reachability_callbacks_dynamically():
    calls = []
    providers = {
        "_is_valid_ping_target_impl": lambda target: calls.append(("valid", target)) or True,
        "_host_is_up_impl": lambda target, timeout, probe_port, **kwargs: calls.append(
            ("up", target, timeout, probe_port, kwargs)
        ) or True,
        "is_valid_ping_target": lambda target: target == "lab-ws-01",
        "WINRM_PORT": 5986,
        "socket": SimpleNamespace(create_connection="connect"),
        "logging": SimpleNamespace(warning="warn"),
    }
    runtime = create_host_discovery_runtime(providers)

    assert runtime.is_valid_ping_target("lab-ws-01") is True
    assert runtime.host_is_up("lab-ws-01", 2.5, 5986) is True
    assert calls[0] == ("valid", "lab-ws-01")
    assert calls[1][0:4] == ("up", "lab-ws-01", 2.5, 5986)
    assert calls[1][4] == {
        "is_valid_target": providers["is_valid_ping_target"],
        "winrm_port": 5986,
        "create_connection": "connect",
        "warn": "warn",
    }
