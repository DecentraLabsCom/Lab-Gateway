from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest

from host_discovery_runtime import HostDiscoveryRuntime, create_host_discovery_runtime
from host_discovery_context import HostDiscoveryContext
from host_discovery_service import discover_labstation_candidate


def _context(*, calls=None):
    calls = calls if calls is not None else []
    state = {"connections": ([{"name": "first"}], None)}
    logger = SimpleNamespace(warning=lambda *args: calls.append(("warning", args)))
    context = HostDiscoveryContext(
        is_valid_ping_target_impl=lambda target: calls.append(("valid", target)) or True,
        get_is_valid_ping_target=lambda: lambda target: target == "lab-ws-01",
        host_is_up_impl=lambda target, timeout, probe_port, **kwargs: calls.append(
            ("up", target, timeout, probe_port, kwargs)
        ) or True,
        get_winrm_port=lambda: 5986,
        get_create_connection=lambda: cast(Callable[..., Any], "connect"),
        get_logger=lambda: logger,
        normalize_match_key_impl=lambda value: calls.append(("key", value)) or "host",
        tcp_port_open_impl=lambda host, port, timeout, **kwargs: calls.append(
            ("tcp", host, port, timeout, kwargs)
        ) or True,
        get_discovery_timeout=lambda: 1.5,
        response_looks_like_labstation_impl=lambda response: (True, "LabStation"),
        normalize_mac_impl=lambda value, **kwargs: calls.append(
            ("mac", value, kwargs)
        ) or "AA:BB",
        get_mac_pattern=lambda: "mac-pattern",
        parse_boolish_impl=lambda value: bool(value),
        extract_nic_candidates_impl=lambda heartbeat, **kwargs: calls.append(
            ("nics", heartbeat, kwargs)
        ) or [{"mac": "AA:BB"}],
        get_normalize_mac=lambda: lambda value: "AA:BB",
        get_parse_boolish=lambda: bool,
        choose_wol_mac_impl=lambda candidates: calls.append(
            ("choose", candidates)
        ) or candidates[0],
        suggest_mac_from_heartbeat_impl=lambda heartbeat, **kwargs: calls.append(
            ("suggest", heartbeat, kwargs)
        ) or {"mac": "AA:BB"},
        get_discovery_ports=lambda: [8765],
        get_discovery_paths=lambda: ["/health"],
        get_http_get=lambda: cast(Callable[..., Any], "get"),
        get_request_exception=lambda: RuntimeError,
        get_response_classifier=lambda: lambda response: (True, "LabStation"),
        get_suggest_mac=lambda: lambda heartbeat: {"mac": "AA:BB"},
        probe_labstation_http_impl=lambda host, **kwargs: calls.append(
            ("probe", host, kwargs)
        ) or {"detected": True},
        query_labstation_task_heartbeat_path_impl=lambda host, **kwargs: calls.append(
            ("task-path", host, kwargs)
        ) or r"C:\heartbeat.json",
        get_run_remote_powershell=lambda: cast(Callable[..., Any], "powershell"),
        get_json_loads=lambda: cast(Callable[[str], Any], "loads"),
        build_heartbeat_path_candidates_impl=lambda host, **kwargs: calls.append(
            ("paths", host, kwargs)
        ) or [r"C:\heartbeat.json"],
        get_query_task_path=lambda: lambda host: r"C:\heartbeat.json",
        get_heartbeat_paths=lambda: [r"C:\fallback.json"],
        discover_heartbeat_hint_impl=lambda hostname, **kwargs: calls.append(
            ("hint", hostname, kwargs)
        ) or {"detected": True},
        get_credentials_configured=lambda: lambda _hostname: True,
        get_path_candidates=lambda: lambda host: [r"C:\heartbeat.json"],
        get_read_remote_file=lambda: cast(Callable[..., Any], "read"),
        get_suggested_mac=lambda: lambda heartbeat: {"mac": "AA:BB"},
        guacamole_name_candidates_impl=lambda connection, **kwargs: kwargs[
            "load_connections"
        ]()[0],
        get_load_guacamole_connections=lambda: lambda: state["connections"],
        get_normalize_match_key=lambda: lambda value: str(value or "").strip().lower(),
        resolve_guacamole_connection_impl=lambda connection_id, **kwargs: kwargs[
            "load_connections"
        ]()[0][0],
        discover_labstation_candidate_impl=discover_labstation_candidate,
        get_resolve_dns=lambda: lambda *args, **kwargs: [],
        get_tcp_probe=lambda: lambda *args, **kwargs: True,
        get_http_probe=lambda: lambda host: {"detected": True},
        get_heartbeat_hint=lambda: lambda host: {
            "detected": True,
            "path": "heartbeat.json",
        },
        get_name_candidates=lambda: lambda connection: ["first"],
        get_events_path=lambda: r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    )
    return context, state, calls


def test_host_discovery_runtime_forwards_network_and_heartbeat_dependencies():
    context, _state, calls = _context()
    runtime = create_host_discovery_runtime(context)

    assert isinstance(runtime, HostDiscoveryRuntime)
    assert runtime.is_valid_ping_target("lab-ws-01") is True
    assert runtime.host_is_up("lab-ws-01", 2.5, 5986) is True
    assert runtime.normalize_match_key(" Host ") == "host"
    assert runtime.tcp_port_open("host", 5986) is True
    assert runtime.normalize_mac("raw") == "AA:BB"
    assert runtime.extract_nic_candidates_from_heartbeat({"status": {}}) == [
        {"mac": "AA:BB"}
    ]
    assert runtime.choose_wol_mac([{"mac": "AA:BB"}]) == {"mac": "AA:BB"}
    assert runtime.suggest_mac_from_heartbeat({"status": {}}) == {"mac": "AA:BB"}
    assert runtime.probe_labstation_http("host") == {"detected": True}
    assert runtime.query_labstation_task_heartbeat_path({"name": "host"}) == (
        r"C:\heartbeat.json"
    )
    assert runtime.build_heartbeat_path_candidates({"name": "host"}) == [
        r"C:\heartbeat.json"
    ]
    assert runtime.discover_heartbeat_hint("host") == {"detected": True}
    assert any(call[0] == "hint" for call in calls)


def test_host_discovery_runtime_keeps_guacamole_and_candidate_callbacks_dynamic():
    context, state, _calls = _context()
    runtime = create_host_discovery_runtime(context)

    assert runtime.guacamole_name_candidates({"hostname": "station"}) == [
        {"name": "first"}
    ]
    assert runtime.resolve_guacamole_connection(7) == {"name": "first"}
    result = runtime.discover_labstation_candidate({"hostname": "station"})
    assert result["status"] == "labstation-detected"
    assert result["opsHostDraft"]["nameCandidates"] == ["first"]

    state["connections"] = ([{"name": "second"}], None)
    assert runtime.guacamole_name_candidates({"hostname": "station"}) == [
        {"name": "second"}
    ]


def test_host_discovery_context_is_immutable():
    context, _state, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "get_logger", lambda: SimpleNamespace())
