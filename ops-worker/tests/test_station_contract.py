import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from station_contract import StationContractError, normalize_station_payload
from station_transport import normalize_command_result


CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "station"
V3_ROOT = CONTRACT_ROOT / "v3"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_path",
    [
        V3_ROOT / "fixtures" / "linux" / "status.fixture.json",
        V3_ROOT / "fixtures" / "windows" / "status.fixture.json",
    ],
)
def test_v3_reference_status_fixtures_match_the_canonical_schema_and_normalize(fixture_path):
    schema = _read_json(V3_ROOT / "status.schema.json")
    payload = _read_json(fixture_path)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    normalized = normalize_station_payload(payload)

    assert normalized["contractVersion"] == "3.0.0"
    assert normalized["rawSchemaVersion"] == "3.0.0"
    assert normalized["host"] == payload["host"]
    assert normalized["platform"]["os"] == payload["platform"]["os"]
    assert set(("physicalLab", "wake", "fmu")) <= set(normalized["readiness"])
    assert normalized["sessions"]["active"] == payload["sessions"]["active"]


@pytest.mark.parametrize(
    ("fixture_name", "expected_profile"),
    [("windows-status.fixture.json", "hybrid"), ("windows-heartbeat.fixture.json", "hybrid")],
)
def test_windows_v2_fixtures_project_to_the_same_internal_contract(fixture_name, expected_profile):
    payload = _read_json(CONTRACT_ROOT / "v2" / fixture_name)

    normalized = normalize_station_payload(payload)

    assert normalized["contractVersion"].startswith("2.")
    assert normalized["rawSchemaVersion"].startswith("2.")
    assert normalized["platform"]["os"] == "windows"
    assert normalized["management"]["transport"] == "winrm"
    assert normalized["profile"] == expected_profile
    assert isinstance(normalized["sessions"]["localSessionActive"], bool)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(schemaVersion="4.0.0"), "major"),
        (lambda value: value.update(timestamp="2026-10-06T12:00:00"), "timezone"),
        (lambda value: value.update(profile="desktop"), "profile"),
        (lambda value: value["platform"].update(os="freebsd"), "platform.os"),
        (lambda value: value["management"].update(transport="telnet"), "management.transport"),
        (lambda value: value["management"].update(transport="winrm"), "management.transport"),
        (lambda value: value.update(localModeEnabled="false"), "localModeEnabled"),
        (lambda value: value["readiness"]["wake"].update(available="false"), "readiness.wake"),
        (lambda value: value["readiness"]["fmu"].update(ready=1), "readiness.fmu"),
        (lambda value: value["sessions"].update(active={}), "sessions.active"),
        (lambda value: value.__setitem__("operations", None), "operations"),
    ],
)
def test_v3_rejects_invalid_major_types_and_platform_transport_mismatches(mutate, message):
    payload = _read_json(V3_ROOT / "fixtures" / "linux" / "status.fixture.json")
    mutate(payload)

    with pytest.raises(StationContractError, match=message):
        normalize_station_payload(payload)


def test_v3_requires_every_canonical_envelope_field():
    payload = _read_json(V3_ROOT / "fixtures" / "linux" / "status.fixture.json")
    del payload["operations"]

    with pytest.raises(StationContractError, match="operations"):
        normalize_station_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", "3.1.0"),
        ("summary", {"state": "almost-ready", "ready": True, "issues": []}),
    ],
)
def test_v3_rejects_payloads_that_violate_the_canonical_schema(field, value):
    payload = _read_json(V3_ROOT / "fixtures" / "linux" / "status.fixture.json")
    payload[field] = value

    with pytest.raises(StationContractError, match="schema"):
        normalize_station_payload(payload)


def test_invalid_future_major_fixture_is_rejected_by_the_ingress_normalizer():
    payload = _read_json(V3_ROOT / "fixtures" / "invalid" / "future-major.fixture.json")

    with pytest.raises(StationContractError, match="major"):
        normalize_station_payload(payload)


def test_v3_fixture_is_current_with_both_status_and_heartbeat_schemas():
    status = _read_json(V3_ROOT / "fixtures" / "linux" / "status.fixture.json")
    status_schema = _read_json(V3_ROOT / "status.schema.json")
    heartbeat_schema = _read_json(V3_ROOT / "heartbeat.schema.json")
    Draft202012Validator.check_schema(status_schema)
    Draft202012Validator.check_schema(heartbeat_schema)
    Draft202012Validator(status_schema, format_checker=FormatChecker()).validate(status)


def test_all_canonical_v3_schemas_are_valid_and_accept_reference_payloads():
    status_schema = _read_json(V3_ROOT / "status.schema.json")
    heartbeat_schema = _read_json(V3_ROOT / "heartbeat.schema.json")
    capabilities_schema = _read_json(V3_ROOT / "capabilities.schema.json")
    command_result_schema = _read_json(V3_ROOT / "command-result.schema.json")
    for schema in (status_schema, heartbeat_schema, capabilities_schema, command_result_schema):
        Draft202012Validator.check_schema(schema)

    registry = Registry().with_resource(status_schema["$id"], Resource.from_contents(status_schema))
    capabilities = {
        "platform": {"os": "linux"},
        "profile": "fmu-only",
        "management": {"transport": "ssh", "ready": True},
        "readiness": {
            name: {"available": True, "ready": True, "issues": []}
            for name in ("physicalLab", "wake", "fmu")
        },
    }
    Draft202012Validator(capabilities_schema, registry=registry).validate(capabilities)

    command_result = normalize_command_result(
        "status-json", 1, "", "completed with a warning", 0, "ssh", request_id="operation-1"
    )
    command_result.update({"exit_code": command_result["exitCode"], "duration_ms": command_result["durationMs"]})
    command_result_validator = Draft202012Validator(command_result_schema, format_checker=FormatChecker())
    command_result_validator.validate(command_result)
    command_result["outcome"] = "success"
    with pytest.raises(ValidationError):
        command_result_validator.validate(command_result)
