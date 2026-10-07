from unittest.mock import Mock

import pytest

from station_errors import StationAuthenticationFailed, StationUnreachable
from station_transport_factory import StationTransportRuntime, create_station_transport_runtime


@pytest.fixture
def runtime():
    run = Mock(return_value={"exit_code": 1, "stdout": "done\n", "stderr": "warning", "duration_ms": 8})
    read = Mock(return_value="artifact")
    write = Mock(return_value=True)
    remove = Mock(return_value=True)
    powershell = Mock()
    ssh = Mock()
    return StationTransportRuntime(
        run_winrm_command=run,
        read_winrm_file=read,
        write_winrm_file=write,
        remove_winrm_file=remove,
        run_winrm_powershell=powershell,
        ssh_transport=ssh,
    ), {"run": run, "read": read, "write": write, "remove": remove, "powershell": powershell, "ssh": ssh}


def test_transport_selection_and_winrm_command_normalization(runtime):
    transport, calls = runtime
    host = {"name": "station", "management_transport": "winrm"}
    assert transport.transport_for(host) == "winrm"
    assert transport.transport_for({"management": {"transport": "SSH"}}) == "ssh"
    result = transport.execute(host, "status-json", ["--json"], request_id="req-1")
    assert result["id"] == "req-1"
    assert result["exitCode"] == 1 and result["outcome"] == "warning"
    assert result["transport"] == "winrm" and result["metadata"] == {"platform": "windows"}
    assert result["exit_code"] == 1 and result["duration_ms"] == 8
    calls["run"].assert_called_once_with(host, "status-json", ["--json"])


def test_winrm_legacy_aliases_match_normalized_failure_values(runtime):
    transport, calls = runtime
    calls["run"].return_value = {"exit_code": -1, "stdout": "", "stderr": "invalid result", "duration_ms": -8}

    result = transport.execute({"name": "station", "management_transport": "winrm"}, "status-json", [])

    assert result["exitCode"] == result["exit_code"] == 2
    assert result["durationMs"] == result["duration_ms"] == 0


def test_execute_routes_ssh_and_maps_transport_failures(runtime):
    transport, calls = runtime
    host = {"name": "station", "management": {"transport": "ssh"}}
    calls["ssh"].execute.return_value = {"requestId": "ssh-1", "exitCode": 0, "stdout": "identity", "transport": "ssh"}
    result = transport.execute(host, "identity", [], request_id="ssh-1")
    assert result["requestId"] == "ssh-1" and result["transport"] == "ssh"
    calls["ssh"].execute.assert_called_once_with(host, "identity", [], request_id="ssh-1")

    calls["ssh"].execute.side_effect = StationAuthenticationFailed()
    with pytest.raises(StationAuthenticationFailed):
        transport.execute(host, "identity", [])
    calls["ssh"].execute.side_effect = RuntimeError("private detail")
    with pytest.raises(StationUnreachable) as exc:
        transport.execute(host, "identity", [])
    assert "private detail" not in str(exc.value)
    with pytest.raises(StationUnreachable):
        transport.execute({"management_transport": "telnet"}, "identity", [])


def test_artifact_reads_enforce_allowlist_and_resolve_windows_paths(runtime):
    transport, calls = runtime
    host = {"name": "windows", "heartbeat_path": "C:/station/heartbeat.json", "events_path": "C:/station/events.jsonl"}
    assert transport.read_artifact(host, "heartbeat") == "artifact"
    calls["read"].assert_called_with(host, "C:/station/heartbeat.json", None, None, None, None, None)
    assert transport.read_artifact(host, "session-events") == "artifact"
    assert transport.read_remote_file(host, "C:/station/heartbeat.json", "extra") == "artifact"
    calls["read"].assert_called_with(host, "C:/station/heartbeat.json", "extra")
    with pytest.raises(ValueError, match="allowlisted"):
        transport.read_artifact(host, "secrets")
    with pytest.raises(ValueError, match="not configured"):
        transport.read_artifact({"name": "windows"}, "heartbeat")


def test_ssh_artifacts_map_only_named_contract_files(runtime):
    transport, calls = runtime
    host = {"name": "linux", "management_transport": "ssh", "heartbeat_path": "heartbeat", "events_path": "session-events"}
    calls["ssh"].read_artifact.side_effect = lambda _host, name: name
    assert transport.read_artifact(host, "heartbeat") == "heartbeat"
    assert transport.read_remote_file(host, "status") == "status"
    assert transport.read_remote_file(host, "heartbeat") == "heartbeat"
    assert transport.read_remote_file(host, "session-events") == "session-events"
    with pytest.raises(ValueError, match="logical artifacts"):
        transport.read_remote_file(host, "/etc/passwd")
    with pytest.raises(StationUnreachable):
        calls["ssh"].read_artifact.side_effect = RuntimeError("private")
        transport.read_artifact(host, "heartbeat")


def test_remote_write_delete_are_winrm_only(runtime):
    transport, calls = runtime
    windows = {"management_transport": "winrm"}
    assert transport.write_remote_file(windows, "path", "data") is True
    assert transport.remove_remote_file(windows, "path") is True
    calls["write"].assert_called_once_with(windows, "path", "data")
    calls["remove"].assert_called_once_with(windows, "path")
    linux = {"management_transport": "ssh"}
    with pytest.raises(ValueError, match="not part of the transport contract"):
        transport.write_remote_file(linux, "path", "data")
    with pytest.raises(ValueError, match="not part of the transport contract"):
        transport.remove_remote_file(linux, "path")


def test_probe_uses_each_management_transport(runtime):
    transport, calls = runtime
    calls["ssh"].probe.return_value = {"reachable": True, "transport": "ssh"}
    assert transport.probe({"management_transport": "ssh"})["transport"] == "ssh"
    calls["run"].return_value = {"exitCode": 1}
    assert transport.probe({"management_transport": "winrm"}) == {"reachable": True, "transport": "winrm"}
    calls["run"].return_value = {"exitCode": 2}
    assert transport.probe({"management_transport": "winrm"}) == {"reachable": False, "transport": "winrm"}


def test_secret_operations_validate_and_use_transport_specific_secure_channels(runtime):
    transport, calls = runtime
    windows = {"management_transport": "winrm"}
    token = "s" * 48
    assert transport.write_secret(windows, "fmu-internal-token", token) == {
        "exitCode": 0, "outcome": "success", "transport": "winrm", "secretId": "fmu-internal-token"
    }
    assert token not in calls["powershell"].call_args.kwargs["script"]
    assert transport.clear_secret(windows, "fmu-internal-token")["secretId"] == "fmu-internal-token"
    linux = {"management_transport": "ssh"}
    calls["ssh"].write_secret.return_value = {"exitCode": 0}
    calls["ssh"].clear_secret.return_value = {"exitCode": 0}
    assert transport.write_secret(linux, "fmu-internal-token", token)["exitCode"] == 0
    assert transport.clear_secret(linux, "fmu-internal-token")["exitCode"] == 0
    for secret_id, value in [("other", "secret"), ("fmu-internal-token", ""), ("fmu-internal-token", "x" * 4097)]:
        with pytest.raises(ValueError):
            transport.write_secret(windows, secret_id, value)
    with pytest.raises(ValueError):
        transport.clear_secret(windows, "other")


def test_missing_secure_secret_provisioning_surface_fails_closed():
    no_powershell = StationTransportRuntime(
        run_winrm_command=Mock(), read_winrm_file=Mock(), write_winrm_file=Mock(), remove_winrm_file=Mock()
    )
    with pytest.raises(ValueError, match="not configured"):
        no_powershell.write_secret({"management_transport": "winrm"}, "fmu-internal-token", "valid")
    with pytest.raises(ValueError, match="not configured"):
        no_powershell.clear_secret({"management_transport": "winrm"}, "fmu-internal-token")


def test_factory_returns_station_runtime():
    result = create_station_transport_runtime(
        run_winrm_command=Mock(), read_winrm_file=Mock(), write_winrm_file=Mock(), remove_winrm_file=Mock()
    )
    assert isinstance(result, StationTransportRuntime)
