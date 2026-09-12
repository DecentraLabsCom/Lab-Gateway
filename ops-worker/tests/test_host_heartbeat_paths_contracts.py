import worker


def test_query_labstation_task_heartbeat_path_contract_preserves_script_and_arguments(
    monkeypatch,
):
    host = {"name": "lab-candidate", "address": "lab-candidate"}
    calls = []
    raw = '{"heartbeatPath": "C:\\\\LabStation\\\\heartbeat.json"}'

    class FakeLogger:
        def debug(self, *args):
            calls.append(("debug", *args))

    def run_remote(received_host, script, *args):
        calls.append(("run", received_host, script, args))
        return raw

    monkeypatch.setattr(worker, "run_remote_powershell", run_remote)
    monkeypatch.setattr(worker, "logging", FakeLogger())

    result = worker.query_labstation_task_heartbeat_path(host)

    assert result == r"C:\LabStation\heartbeat.json"
    assert calls[0][0:2] == ("run", host)
    assert calls[0][2].startswith("\n$task = Get-ScheduledTask")
    assert "-TaskPath '\\LabStation\\'" in calls[0][2]
    assert "-TaskName 'BackgroundService'" in calls[0][2]
    assert "LabStation\\.ahk" in calls[0][2]
    assert "ConvertTo-Json -Compress" in calls[0][2]
    assert calls[0][3] == (None, None, None, None, None)


def test_query_labstation_task_heartbeat_path_contract_fails_closed_and_logs_debug(
    monkeypatch,
):
    failure = RuntimeError("scheduled task unavailable")
    calls = []

    class FakeLogger:
        def debug(self, *args):
            calls.append(args)

    monkeypatch.setattr(
        worker,
        "run_remote_powershell",
        lambda *_args: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(worker, "logging", FakeLogger())

    assert worker.query_labstation_task_heartbeat_path({"name": "lab"}) is None
    assert calls == [
        ("Unable to derive Lab Station heartbeat path from scheduled task: %s", failure)
    ]


def test_build_heartbeat_path_candidates_contract_preserves_task_priority_and_deduplication(
    monkeypatch,
):
    host = {"name": "lab-candidate"}
    derived_path = r"D:\Installed\heartbeat.json"
    configured_paths = [
        r"C:\Default\heartbeat.json",
        derived_path,
        r"E:\Fallback\heartbeat.json",
        r"C:\Default\heartbeat.json",
    ]
    calls = []

    monkeypatch.setattr(worker, "DISCOVERY_HEARTBEAT_PATHS", configured_paths)
    monkeypatch.setattr(
        worker,
        "query_labstation_task_heartbeat_path",
        lambda received_host: calls.append(received_host) or derived_path,
    )

    assert worker.build_heartbeat_path_candidates(host) == [
        derived_path,
        r"C:\Default\heartbeat.json",
        r"E:\Fallback\heartbeat.json",
    ]
    assert calls == [host]
