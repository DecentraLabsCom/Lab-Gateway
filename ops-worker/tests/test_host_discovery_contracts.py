import worker


def test_discover_labstation_candidate_contract_preserves_signal_order_and_payload(
    monkeypatch,
):
    connection = {
        "id": 7,
        "name": "Lab Candidate",
        "hostname": "lab-candidate",
        "port": "3389",
    }
    calls = []
    http_result = {
        "checked": True,
        "detected": True,
        "url": "http://lab-candidate:8765/labstation/health",
        "statusCode": 200,
        "service": "LabStation",
        "suggestedMac": {"mac": "AA:BB:CC:DD:EE:FF", "source": "http"},
    }
    heartbeat_result = {
        "checked": True,
        "detected": True,
        "status": "ok",
        "path": r"C:\LabStation\heartbeat.json",
        "suggestedMac": {"mac": "00:11:22:33:44:55", "source": "heartbeat"},
    }

    def resolve_dns(host, port):
        calls.append(("dns", host, port))
        return []

    def tcp_probe(host, port, timeout=None):
        calls.append(("tcp", host, port, timeout))
        return True

    def http_probe(host):
        calls.append(("http", host))
        return http_result

    def heartbeat_hint(host):
        calls.append(("heartbeat", host))
        return heartbeat_result

    def name_candidates(received_connection):
        calls.append(("names", received_connection))
        return ["Lab Candidate", "lab-candidate"]

    monkeypatch.setattr(worker, "WINRM_PORT", 55986)
    monkeypatch.setattr(worker, "DISCOVERY_TIMEOUT_SECONDS", 1.25)
    monkeypatch.setattr(worker, "DISCOVERY_HEARTBEAT_PATHS", [r"C:\Default\heartbeat.json"])
    monkeypatch.setattr(worker.socket, "getaddrinfo", resolve_dns)
    monkeypatch.setattr(worker, "tcp_port_open", tcp_probe)
    monkeypatch.setattr(worker, "probe_labstation_http", http_probe)
    monkeypatch.setattr(worker, "discover_heartbeat_hint", heartbeat_hint)
    monkeypatch.setattr(worker, "guacamole_name_candidates", name_candidates)

    result = worker.discover_labstation_candidate(connection)

    assert calls == [
        ("dns", "lab-candidate", None),
        ("tcp", "lab-candidate", 55986, 1.25),
        ("http", "lab-candidate"),
        ("heartbeat", "lab-candidate"),
        ("names", connection),
    ]
    assert result == {
        "connection": connection,
        "status": "labstation-detected",
        "checks": {
            "dns": True,
            "winrm": {"55986": True},
            "labStationHttp": http_result,
            "heartbeat": heartbeat_result,
        },
        "opsHostDraft": {
            "name": "lab-candidate",
            "address": "lab-candidate",
            "winrm_transport": "ntlm",
            "winrm_use_ssl": True,
            "winrm_port": 5986,
            "heartbeat_path": r"C:\LabStation\heartbeat.json",
            "events_path": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
            "labs": [],
            "nameCandidates": ["Lab Candidate", "lab-candidate"],
            "mac": "AA:BB:CC:DD:EE:FF",
        },
    }


def test_discover_labstation_candidate_contract_preserves_missing_hostname_response(
    monkeypatch,
):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("discovery probes must not run without a hostname")

    monkeypatch.setattr(worker, "tcp_port_open", fail_if_called)
    monkeypatch.setattr(worker, "probe_labstation_http", fail_if_called)
    monkeypatch.setattr(worker, "discover_heartbeat_hint", fail_if_called)
    monkeypatch.setattr(worker, "guacamole_name_candidates", fail_if_called)

    assert worker.discover_labstation_candidate({"id": 8}) == {
        "connection": {"id": 8},
        "status": "missing-hostname",
        "checks": {
            "dns": False,
            "winrm": {},
            "labStationHttp": {
                "checked": False,
                "detected": False,
                "status": "missing-hostname",
            },
        },
    }
