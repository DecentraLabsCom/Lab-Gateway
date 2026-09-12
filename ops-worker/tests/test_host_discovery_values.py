import json

import host_discovery_values


class Response:
    status_code = 200
    text = ""

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_response_classifier_detects_labstation_and_reports_service_name():
    detected, service = host_discovery_values.response_looks_like_labstation(
        Response({"service": "LabStation", "version": "1"})
    )

    assert detected is True
    assert service == "LabStation"


def test_http_probe_checks_configured_endpoints_and_adds_mac_hint():
    calls = []

    def http_get(url, timeout):
        calls.append((url, timeout))
        return Response({"service": "LabStation", "status": {"wake": {"nicPower": []}}})

    result = host_discovery_values.probe_labstation_http(
        "station.example",
        ports=[8765],
        paths=["/health"],
        timeout=2.5,
        http_get=http_get,
        request_exception_type=OSError,
        response_classifier=host_discovery_values.response_looks_like_labstation,
        suggest_mac=lambda _body: {"mac": "00:11:22:33:44:55"},
    )

    assert calls == [("http://station.example:8765/health", 2.5)]
    assert result["detected"] is True
    assert result["suggestedMac"]["mac"] == "00:11:22:33:44:55"


def test_http_probe_keeps_missing_host_and_no_response_contracts():
    get = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline"))

    assert host_discovery_values.probe_labstation_http(
        "",
        ports=[8765],
        paths=["/health"],
        timeout=1,
        http_get=get,
        request_exception_type=OSError,
        response_classifier=host_discovery_values.response_looks_like_labstation,
        suggest_mac=lambda _body: None,
    ) == {"checked": False, "detected": False, "status": "missing-hostname"}
    assert host_discovery_values.probe_labstation_http(
        "station.example",
        ports=[8765],
        paths=["/health"],
        timeout=1,
        http_get=get,
        request_exception_type=OSError,
        response_classifier=host_discovery_values.response_looks_like_labstation,
        suggest_mac=lambda _body: None,
    ) == {"checked": True, "detected": False, "status": "no-response"}
