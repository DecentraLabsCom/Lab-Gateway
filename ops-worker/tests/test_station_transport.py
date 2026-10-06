import json

import pytest

from station_errors import StationCommandRejected, StationUnreachable
from station_transport import normalize_command_result, validate_station_command
from station_transport_factory import StationTransportRuntime


@pytest.mark.parametrize(
    ("exit_code", "outcome", "success"),
    [(0, "success", True), (1, "warning", True), (2, "failure", False), (255, "failure", False), (-1, "failure", False)],
)
def test_command_result_normalization_preserves_the_station_exit_contract(exit_code, outcome, success):
    result = normalize_command_result("status-json", exit_code, " first\n last \n", "", -10, "ssh", request_id="request-1")

    assert result["outcome"] == outcome
    assert result["success"] is success
    assert result["exitCode"] == max(exit_code, 2) if exit_code < 0 else result["exitCode"] == exit_code
    assert result["message"] == "last"
    assert result["durationMs"] == 0
    assert result["id"] == "request-1"
    assert result["transport"] == "ssh"


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("identity", []),
        ("status-json", []),
        ("prepare-session", ["--guard-grace=0", "--guard-notify=false"]),
        ("release-session", ["--reboot=false"]),
        ("session guard", ["--user=teacher_1"]),
        ("power", ["shutdown", "--require-wake"]),
        ("recovery reboot-if-needed", ["--force", "--timeout=10"]),
        ("local-mode", ["set", "--ttl=60"]),
        ("service", ["status"]),
        ("fmu-executor", ["restart"]),
        ("artifact.read", ["heartbeat"]),
    ],
)
def test_station_transport_accepts_each_documented_operation(command, args):
    validate_station_command(command, args)


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("shell", ["-c", "id"]),
        ("status-json", ["--host=x"]),
        ("prepare-session", ["--unknown"]),
        ("prepare-session", ["--guard-message=hello\nid"]),
        ("session guard", ["--user=../root"]),
        ("power", ["reboot"]),
        ("power", ["shutdown", "--delay=1;id"]),
        ("recovery reboot-if-needed", ["--command=id"]),
        ("local-mode", ["set", "--ttl=1"]),
        ("artifact.read", ["../../etc/passwd"]),
        ("identity", ["ignored"]),
    ],
)
def test_station_transport_rejects_shells_unknown_flags_and_arbitrary_artifacts(command, args):
    with pytest.raises(StationCommandRejected):
        validate_station_command(command, args)


def test_station_transport_rejects_non_string_args_and_excessive_option_count():
    with pytest.raises(StationCommandRejected):
        validate_station_command("prepare-session", ["--guard-grace=" + "x" * 300])
    with pytest.raises(StationCommandRejected):
        validate_station_command("prepare-session", ["--guard-grace=0"] * 13)


def test_legacy_winrm_contract_remains_normalized_and_preserves_historical_keys():
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: {"exit_code": 1, "stdout": "prepared", "stderr": "notice", "duration_ms": 17},
        read_winrm_file=lambda *args: "{}",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
    )

    result = runtime.execute({"name": "windows-station"}, "prepare-session", [], request_id="winrm-1")

    assert result["transport"] == "winrm"
    assert result["outcome"] == "warning"
    assert result["exit_code"] == 1
    assert result["duration_ms"] == 17
    assert result["metadata"]["platform"] == "windows"


def test_transport_selection_is_explicit_and_does_not_fallback_from_unsupported_values():
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: pytest.fail("unsupported transport fell back to WinRM"),
        read_winrm_file=lambda *args: "",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
    )

    assert runtime.transport_for({"management": {"transport": "SSH"}}) == "ssh"
    with pytest.raises(StationUnreachable):
        runtime.execute({"management": {"transport": "telnet"}}, "status-json", [])


def test_ssh_transport_forbids_arbitrary_files_and_remote_mutation():
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: {},
        read_winrm_file=lambda *args: "",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
    )
    host = {"management": {"transport": "ssh"}}

    with pytest.raises(ValueError, match="logical artifacts"):
        runtime.read_remote_file(host, "/etc/shadow")
    with pytest.raises(ValueError, match="not part of"):
        runtime.write_remote_file(host, "path", "content")
    with pytest.raises(ValueError, match="not part of"):
        runtime.remove_remote_file(host, "path")


def test_ssh_artifact_aliases_map_only_known_logical_names(monkeypatch):
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: {},
        read_winrm_file=lambda *args: "",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
        ssh_transport=type("Ssh", (), {"read_artifact": lambda self, host, name: name})(),
    )
    host = {"management": {"transport": "ssh"}}

    assert runtime.read_remote_file(host, "heartbeat") == "heartbeat"
    assert runtime.read_remote_file(host, "session-events") == "session-events"
    with pytest.raises(ValueError, match="arbitrary remote files"):
        runtime.read_remote_file(host, "/tmp/arbitrary")


def test_winrm_fmu_secret_enrollment_sends_only_a_base64_script(monkeypatch):
    secret = "internal-token-that-must-not-be-an-argv"
    calls = []
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: {},
        read_winrm_file=lambda *args: "",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
        run_winrm_powershell=lambda **kwargs: calls.append(kwargs),
    )

    result = runtime.write_secret({"name": "win-station"}, "fmu-internal-token", secret)

    assert result["exitCode"] == 0
    assert len(calls) == 1
    assert secret not in calls[0]["script"]
    assert "FMU_INTERNAL_TOKEN" in calls[0]["script"]
    assert "base64" in calls[0]["script"].lower()


@pytest.mark.parametrize("bad_secret", ["", "x" * 4097])
def test_secret_provisioning_rejects_missing_or_oversized_values_before_transport(bad_secret):
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *args, **kwargs: {},
        read_winrm_file=lambda *args: "",
        write_winrm_file=lambda *args: None,
        remove_winrm_file=lambda *args: None,
    )
    with pytest.raises(ValueError, match="secret operation"):
        runtime.write_secret({"management": {"transport": "ssh"}}, "fmu-internal-token", bad_secret)
