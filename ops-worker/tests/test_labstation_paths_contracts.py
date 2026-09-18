import labstation_paths


def test_resolve_labstation_paths_derives_all_artifacts_from_spaced_heartbeat_path():
    host = {
        "heartbeat_path": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
        "events_path": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    }

    resolved = labstation_paths.resolve_labstation_paths(host)

    assert resolved == {
        "labstation_exe": r"C:\Lab Station\LabStation.exe",
        "local_mode_flag_path": r"C:\Lab Station\labstation\data\local-mode.flag",
        "heartbeat_path": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
        "events_path": r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl",
    }


def test_resolve_labstation_paths_preserves_legacy_root_when_heartbeat_uses_it():
    host = {
        "heartbeat_path": r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
    }

    resolved = labstation_paths.resolve_labstation_paths(host)

    assert resolved["labstation_exe"] == r"C:\LabStation\LabStation.exe"
    assert resolved["local_mode_flag_path"] == r"C:\LabStation\labstation\data\local-mode.flag"
    assert resolved["events_path"] == r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl"


def test_resolve_labstation_paths_uses_current_default_when_no_path_is_configured():
    resolved = labstation_paths.resolve_labstation_paths({})

    assert resolved["labstation_exe"] == r"C:\Lab Station\LabStation.exe"
    assert resolved["heartbeat_path"] == r"C:\Lab Station\labstation\data\telemetry\heartbeat.json"

