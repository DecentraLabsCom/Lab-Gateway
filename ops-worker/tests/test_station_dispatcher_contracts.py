import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest


ROOT = Path(__file__).resolve().parents[2]
V1_SCHEMA_PATH = ROOT / "contracts" / "station" / "dispatcher" / "v1" / "request.schema.json"
V2_SCHEMA_PATH = ROOT / "contracts" / "station" / "dispatcher" / "v2" / "request.schema.json"
V2_RESPONSE_SCHEMA_PATH = ROOT / "contracts" / "station" / "dispatcher" / "v2" / "response.schema.json"


def _validator(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_dispatcher_request_schemas_are_valid_and_accept_v1_and_v2_fixtures():
    v1 = _validator(V1_SCHEMA_PATH)
    v2 = _validator(V2_SCHEMA_PATH)
    v1_request = {"schemaVersion": 1, "id": "identity-1", "operation": "execute", "command": "identity", "args": []}
    for path in (ROOT / "contracts" / "station" / "dispatcher" / "fixtures").glob("*-v2.fixture.json"):
        v2_request = json.loads(path.read_text(encoding="utf-8"))
        assert list(v2.iter_errors(v2_request)) == [], path.name
    assert list(v1.iter_errors(v1_request)) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request.update(schemaVersion=1),
        lambda request: request.update(context={**request["context"], "admin": True}),
        lambda request: request.update(executeBefore="not-a-date"),
        lambda request: request["context"].update(leaseId="../other-station"),
        lambda request: request.update(operationId="status-on-prepare"),
    ],
)
def test_dispatcher_v2_schema_rejects_downgrade_extra_fields_and_bad_values(mutate):
    validator = _validator(V2_SCHEMA_PATH)
    fixture = ROOT / "contracts" / "station" / "dispatcher" / "fixtures" / "prepare-v2.fixture.json"
    request = json.loads(fixture.read_text(encoding="utf-8"))
    invalid = copy.deepcopy(request)
    mutate(invalid)
    assert list(validator.iter_errors(invalid))


def test_operation_status_schema_rejects_extra_dispatch_execution_fields():
    validator = _validator(V2_SCHEMA_PATH)
    path = ROOT / "contracts" / "station" / "dispatcher" / "fixtures" / "operation-status-v2.fixture.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    request["context"] = {"leaseId": "demo:jti"}
    assert list(validator.iter_errors(request))


def test_dispatcher_v2_response_schema_accepts_success_warning_and_failure_fixtures():
    validator = _validator(V2_RESPONSE_SCHEMA_PATH)
    fixtures = ROOT / "contracts" / "station" / "dispatcher" / "fixtures"
    for path in sorted(fixtures.glob("*-v2-response.fixture.json")):
        response = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(response)) == [], path.name


def test_dispatcher_v2_response_schema_rejects_inconsistent_exit_contract():
    validator = _validator(V2_RESPONSE_SCHEMA_PATH)
    fixture = ROOT / "contracts" / "station" / "dispatcher" / "fixtures" / "prepare-v2-response.fixture.json"
    response = json.loads(fixture.read_text(encoding="utf-8"))
    response["success"] = False
    assert list(validator.iter_errors(response))
