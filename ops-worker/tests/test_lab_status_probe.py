from datetime import datetime, timezone

from lab_status_probe import CachedLabTargetProber, normalize_lab_status_target


NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)


def test_normalize_target_uses_protocol_default_and_rejects_untrusted_values():
    assert normalize_lab_status_target({
        "labId": "7",
        "protocol": "rdp",
        "hostname": "windows-01",
    }) == {
        "labId": "7",
        "protocol": "rdp",
        "hostname": "windows-01",
        "port": 3389,
    }
    assert normalize_lab_status_target({
        "labId": "8",
        "protocol": "telnet",
        "hostname": "linux-01",
    }) is None
    assert normalize_lab_status_target({
        "labId": "9",
        "protocol": "ssh",
        "hostname": "https://internal.example",
        "port": 22,
    }) is None


def test_cached_prober_limits_probe_to_catalog_target_and_reuses_recent_result():
    calls = []
    clock = [100.0]
    prober = CachedLabTargetProber(
        tcp_port_open=lambda host, port, timeout: calls.append((host, port, timeout)) or True,
        timeout_seconds=1.5,
        cache_seconds=30,
        now=lambda: NOW,
        monotonic=lambda: clock[0],
    )
    target = {"labId": "7", "protocol": "rdp", "hostname": "windows-01"}

    first = prober.probe_targets([target])
    second = prober.probe_targets([target])

    assert first["7"]["signal"] == "reachable"
    assert first["7"]["source"] == "guacamole_tcp_probe"
    assert second == first
    assert calls == [("windows-01", 3389, 1.5)]


def test_cached_prober_reports_tcp_failure_without_returning_target_details():
    prober = CachedLabTargetProber(
        tcp_port_open=lambda *_args: False,
        timeout_seconds=1,
        cache_seconds=30,
        now=lambda: NOW,
        monotonic=lambda: 100.0,
    )

    result = prober.probe_targets([{
        "labId": "8",
        "protocol": "ssh",
        "hostname": "linux-01",
    }])["8"]

    assert result == {
        "signal": "unreachable",
        "reason": "target_unreachable",
        "source": "guacamole_tcp_probe",
        "observedAt": "2026-09-23T10:00:00Z",
    }
    assert "linux-01" not in str(result)
