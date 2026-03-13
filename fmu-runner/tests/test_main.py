"""
Tests for FMU Runner — main.py

Uses pytest + httpx (TestClient for FastAPI).
Mocks fmpy functions and JWT auth to test endpoints in isolation.
"""

import json
import time
import zipfile
import io
import hashlib
import hmac
from collections import defaultdict, deque
from xml.etree import ElementTree as ET
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from fmpy import read_model_description

# Patch auth before importing main so the import doesn't fail
with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": 1, "accessKey": "test.fmu"}):
    from main import (
        app,
        _init_db,
        HISTORY_DB_PATH,
        _effective_timeout_seconds,
        MAX_SIMULATION_TIMEOUT,
        _build_proxy_model_description_xml,
        _validate_proxy_generation_supported,
    )
    from auth import verify_jwt as _original_verify_jwt


# Override FastAPI dependency so all endpoints skip real JWT validation
def _fake_jwt(**claims):
    """Return a callable that FastAPI will use as the verify_jwt dependency."""
    merged = {"sub": "test-user", "labId": 1, "accessKey": "test.fmu"}
    merged.update(claims)
    # Remove keys explicitly set to None
    merged = {k: v for k, v in merged.items() if v is not None}
    async def _override():
        return merged
    return _override


app.dependency_overrides[_original_verify_jwt] = _fake_jwt()

client = TestClient(app)


# ─── /health ─────────────────────────────────────────────────────────

def test_health_returns_status():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("UP", "DEGRADED")
    assert "checks" in data
    assert "fmuCount" in data


# ─── /api/v1/simulations/describe ───────────────────────────────────

class MockModelDescription:
    """Fake FMPy model description."""
    fmiVersion = "2.0"
    coSimulation = True
    modelExchange = False

    class defaultExperiment:
        startTime = 0.0
        stopTime = 10.0
        stepSize = 0.01

    class _Var:
        def __init__(self, name, causality, type_, unit=None, start=None):
            self.name = name
            self.causality = causality
            self.type = type_
            self.unit = unit
            self.start = start
            self.min = None
            self.max = None

    modelVariables = [
        _Var("mass", "input", "Real", "kg", 1.0),
        _Var("position", "output", "Real", "m"),
    ]


class MockFmi3ModelDescription:
    fmiVersion = "3.0"
    guid = "{fmi3-guid}"
    instantiationToken = "{fmi3-guid}"
    coSimulation = True
    modelExchange = False

    class defaultExperiment:
        startTime = 0.0
        stopTime = 5.0
        stepSize = 0.1

    class _Var:
        def __init__(self, name, causality, type_, start=None, initial=None, dimensions=None, variability=None):
            self.name = name
            self.causality = causality
            self.type = type_
            self.start = start
            self.initial = initial
            self.unit = None
            self.min = None
            self.max = None
            self.variability = variability or "continuous"
            self.valueReference = 0 if name == "time" else 1
            self.dimensions = dimensions or []

    modelVariables = [
        _Var("time", "independent", "Float64"),
        _Var("counter", "output", "Int32", start=1, initial="exact", variability="discrete"),
    ]


class MockFmi3WideIntegerDescription:
    fmiVersion = "3.0"
    guid = "{fmi3-wide-guid}"
    instantiationToken = "{fmi3-wide-guid}"
    coSimulation = True
    modelExchange = False

    class defaultExperiment:
        startTime = 0.0
        stopTime = 2.0
        stepSize = 0.1

    class _Var:
        def __init__(self, name, causality, type_, start=None):
            self.name = name
            self.causality = causality
            self.type = type_
            self.start = start
            self.initial = "exact"
            self.unit = None
            self.min = None
            self.max = None
            self.variability = "discrete"
            self.valueReference = 1 if name == "wideSigned" else 2
            self.dimensions = []

    modelVariables = [
        _Var("wideSigned", "parameter", "Int64", start=-9223372036854775808),
        _Var("wideUnsigned", "parameter", "UInt64", start=18446744073709551615),
    ]


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._resolve_fmu_path")
def test_describe_returns_model_metadata(mock_resolve, mock_read):
    mock_resolve.return_value = "/fake/path/test.fmu"

    response = client.get("/api/v1/simulations/describe?fmuFileName=test.fmu")
    assert response.status_code == 200

    data = response.json()
    assert data["fmiVersion"] == "2.0"
    assert data["simulationType"] == "CoSimulation"
    assert data["supportsCoSimulation"] is True
    assert data["supportsModelExchange"] is False
    assert data["defaultStartTime"] == 0.0
    assert data["defaultStopTime"] == 10.0
    assert len(data["modelVariables"]) == 2
    assert data["modelVariables"][0]["name"] == "mass"
    assert data["modelVariables"][0]["causality"] == "input"


@patch("main.read_model_description", return_value=MockFmi3WideIntegerDescription())
@patch("main._resolve_fmu_path")
def test_describe_preserves_exact_fmi3_int64_and_uint64_starts(mock_resolve, mock_read):
    mock_resolve.return_value = "/fake/path/wide.fmu"
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(accessKey="wide.fmu", resourceType="fmu")
    try:
        response = client.get("/api/v1/simulations/describe?fmuFileName=wide.fmu")
        assert response.status_code == 200

        data = response.json()
        variables = {item["name"]: item for item in data["modelVariables"]}
        assert variables["wideSigned"]["start"] == "-9223372036854775808"
        assert variables["wideUnsigned"]["start"] == "18446744073709551615"
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


def test_describe_requires_fmuFileName():
    response = client.get("/api/v1/simulations/describe")
    assert response.status_code == 422  # FastAPI validation error


def test_proxy_model_description_preserves_zero_value_reference():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyDemo",
        "guid": "{proxy-guid}",
        "modelVariables": [
            {
                "name": "u",
                "type": "Real",
                "causality": "input",
                "variability": "continuous",
                "valueReference": 0,
            },
            {
                "name": "y",
                "type": "Real",
                "causality": "output",
                "variability": "continuous",
                "valueReference": 2,
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    scalar_variables = root.findall("./ModelVariables/ScalarVariable")
    assert scalar_variables[0].attrib["valueReference"] == "0"


def test_proxy_model_description_preserves_initial_and_start_when_exact():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyDemo",
        "guid": "{proxy-guid}",
        "modelVariables": [
            {
                "name": "u",
                "type": "Real",
                "causality": "input",
                "variability": "continuous",
                "valueReference": 0,
                "start": 1.5,
                "initial": "exact",
            },
            {
                "name": "y",
                "type": "Real",
                "causality": "output",
                "variability": "continuous",
                "valueReference": 2,
                "start": 3.0,
                "initial": "exact",
            },
            {
                "name": "dy",
                "type": "Real",
                "causality": "local",
                "variability": "continuous",
                "valueReference": 3,
                "start": 9.0,
                "initial": "calculated",
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    scalar_variables = root.findall("./ModelVariables/ScalarVariable")
    input_real = scalar_variables[0].find("./Real")
    output_real = scalar_variables[1].find("./Real")
    local_real = scalar_variables[2].find("./Real")

    assert input_real is not None
    assert input_real.attrib["start"] == "1.5"
    assert scalar_variables[0].attrib["initial"] == "exact"
    assert output_real is not None
    assert output_real.attrib["start"] == "3.0"
    assert scalar_variables[1].attrib["initial"] == "exact"
    assert local_real is not None
    assert "start" not in local_real.attrib
    assert scalar_variables[2].attrib["initial"] == "calculated"


def test_proxy_model_description_preserves_fmi2_enumeration_declared_type_definitions():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyEnumDemo",
        "guid": "{proxy-guid}",
        "fmiVersion": "2.0",
        "modelVariables": [
            {
                "name": "Enumeration_input",
                "type": "Enumeration",
                "causality": "input",
                "variability": "discrete",
                "valueReference": 33,
                "start": 1,
                "declaredType": {
                    "name": "Option",
                    "type": "Enumeration",
                    "items": [
                        {"name": "Option 1", "value": "1", "description": "First option"},
                        {"name": "Option 2", "value": "2", "description": "Second option"},
                    ],
                },
            },
            {
                "name": "Enumeration_output",
                "type": "Enumeration",
                "causality": "output",
                "variability": "discrete",
                "valueReference": 34,
                "initial": "calculated",
                "declaredType": {
                    "name": "Option",
                    "type": "Enumeration",
                    "items": [
                        {"name": "Option 1", "value": "1", "description": "First option"},
                        {"name": "Option 2", "value": "2", "description": "Second option"},
                    ],
                },
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    type_definition = root.find("./TypeDefinitions/SimpleType[@name='Option']/Enumeration")
    enumeration_input = root.find("./ModelVariables/ScalarVariable[@name='Enumeration_input']/Enumeration")
    enumeration_output = root.find("./ModelVariables/ScalarVariable[@name='Enumeration_output']/Enumeration")

    assert type_definition is not None
    items = type_definition.findall("./Item")
    assert len(items) == 2
    assert items[0].attrib["name"] == "Option 1"
    assert items[0].attrib["value"] == "1"
    assert enumeration_input is not None
    assert enumeration_input.attrib["declaredType"] == "Option"
    assert enumeration_input.attrib["start"] == "1"
    assert enumeration_output is not None
    assert enumeration_output.attrib["declaredType"] == "Option"


def test_proxy_model_description_generates_fmi3_model_description():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyDemoFmi3",
        "guid": "{proxy-guid}",
        "instantiationToken": "{proxy-guid}",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {
                "name": "time",
                "type": "Float64",
                "causality": "independent",
                "variability": "continuous",
                "valueReference": 0,
            },
            {
                "name": "counter",
                "type": "Int32",
                "causality": "output",
                "variability": "discrete",
                "valueReference": 1,
                "initial": "exact",
                "start": 1,
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    assert root.attrib["fmiVersion"] == "3.0"
    assert root.attrib["instantiationToken"] == "{proxy-guid}"
    assert root.find("./CoSimulation").attrib["modelIdentifier"] == "decentralabs_proxy"
    assert root.find("./ModelVariables/ScalarVariable") is None
    assert root.find("./ModelVariables/Float64").attrib["name"] == "time"
    assert root.find("./ModelVariables/Int32").attrib["name"] == "counter"
    assert root.find("./ModelStructure/Output").attrib["valueReference"] == "1"


def test_proxy_model_description_generates_fmi3_dimensioned_variables():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyArrayFmi3",
        "instantiationToken": "{proxy-guid}",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {
                "name": "m",
                "type": "UInt64",
                "causality": "structuralParameter",
                "variability": "fixed",
                "valueReference": 1,
                "start": 3,
            },
            {
                "name": "u",
                "type": "Float64",
                "causality": "input",
                "variability": "continuous",
                "valueReference": 9,
                "start": [1, 2, 3],
                "dimensions": [{"valueReference": 1}],
            },
            {
                "name": "y",
                "type": "Float64",
                "causality": "output",
                "variability": "continuous",
                "valueReference": 10,
                "dimensions": [{"valueReference": 1}],
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    m = root.find("./ModelVariables/UInt64")
    u = root.find("./ModelVariables/Float64[@name='u']")
    y = root.find("./ModelVariables/Float64[@name='y']")

    assert m is not None
    assert m.attrib["start"] == "3"
    assert u is not None
    assert u.attrib["start"] == "1 2 3"
    assert u.find("./Dimension").attrib["valueReference"] == "1"
    assert y is not None
    assert y.find("./Dimension").attrib["valueReference"] == "1"


def test_proxy_model_description_generates_fmi3_binary_and_clock_variables():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyFmi3BinaryClock",
        "instantiationToken": "{proxy-guid}",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {
                "name": "blob",
                "type": "Binary",
                "causality": "input",
                "variability": "discrete",
                "valueReference": 11,
                "start": b"\x01\x02",
            },
            {
                "name": "tick",
                "type": "Clock",
                "causality": "output",
                "variability": "discrete",
                "valueReference": 12,
                "start": True,
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    assert root.find("./ModelVariables/Binary").attrib["start"] == "AQI="
    assert root.find("./ModelVariables/Clock").attrib["start"] == "true"


def test_validate_proxy_generation_supports_extended_fmi3_integer_types():
    metadata = {
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {"name": "i8", "type": "Int8", "valueReference": 1},
            {"name": "u8", "type": "UInt8", "valueReference": 2},
            {"name": "i16", "type": "Int16", "valueReference": 3},
            {"name": "u16", "type": "UInt16", "valueReference": 4},
            {"name": "u32", "type": "UInt32", "valueReference": 5},
            {"name": "i64", "type": "Int64", "valueReference": 6},
            {"name": "u64", "type": "UInt64", "valueReference": 7},
        ],
    }

    _validate_proxy_generation_supported(metadata)


def test_validate_proxy_generation_supports_fmi3_binary_and_clock_types():
    metadata = {
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {"name": "blob", "type": "Binary", "valueReference": 1},
            {"name": "tick", "type": "Clock", "valueReference": 2},
        ],
    }

    _validate_proxy_generation_supported(metadata)


def test_validate_proxy_generation_rejects_dimensioned_clock_for_fmi3_proxy():
    metadata = {
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {
                "name": "tick",
                "type": "Clock",
                "valueReference": 1,
                "dimensions": [{"start": 2}],
            },
        ],
    }

    with pytest.raises(HTTPException) as exc:
        _validate_proxy_generation_supported(metadata)
    assert exc.value.status_code == 422
    assert "Clock" in exc.value.detail


# ─── /api/v1/simulations/run ────────────────────────────────────────

import numpy as np


def _make_sim_result():
    """Create a fake numpy structured array like FMPy returns."""
    dt = np.dtype([("time", float), ("position", float), ("velocity", float)])
    arr = np.array([(0.0, 0.0, 0.0), (0.1, 0.15, 0.98), (0.2, 0.35, 1.1)], dtype=dt)
    return arr


def _make_run_result(fmi_type="CoSimulation"):
    """Return the dict that _run_simulation would produce."""
    return {
        "time": [0.0, 0.1, 0.2],
        "outputs": {"position": [0.0, 0.15, 0.35], "velocity": [0.0, 0.98, 1.1]},
        "outputVariables": ["position", "velocity"],
    }


def _make_future(result):
    """Wrap a value in a resolved Future so the executor mock works."""
    from concurrent.futures import Future
    f = Future()
    f.set_result(result)
    return f


def _make_delayed_future(result, delay_sec=0.1):
    """Return a Future that resolves after *delay_sec* seconds."""
    from concurrent.futures import Future
    from threading import Timer
    f = Future()
    def _set_result_if_pending():
        if not f.done():
            f.set_result(result)
    Timer(delay_sec, _set_result_if_pending).start()
    return f


def test_effective_timeout_caps_to_configured_max_without_exp():
    assert _effective_timeout_seconds(MAX_SIMULATION_TIMEOUT + 100, {}) == MAX_SIMULATION_TIMEOUT


def test_effective_timeout_caps_to_jwt_exp():
    with patch("main.time.time", return_value=1000.0):
        assert _effective_timeout_seconds(120, {"exp": 1005}) == 5


def test_effective_timeout_rejects_expired_jwt():
    with patch("main.time.time", return_value=1000.0):
        with pytest.raises(HTTPException) as exc:
            _effective_timeout_seconds(120, {"exp": 999})
        assert exc.value.status_code == 401


@patch("main._resolve_fmu_path")
@patch("main.read_model_description")
@patch("main._executor")
def test_run_executes_simulation(mock_exec, mock_md, mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"
    md_obj = MagicMock(); md_obj.coSimulation = True; md_obj.modelExchange = False
    mock_md.return_value = md_obj
    mock_exec.submit.return_value = _make_future(_make_run_result())

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {"mass": 1.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.1},
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "time" in data
    assert "outputs" in data
    assert "position" in data["outputs"]
    assert "simId" in data
    assert data["fmiType"] == "CoSimulation"


@patch("main._resolve_fmu_path")
def test_run_rejects_invalid_time_range(mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {},
        "options": {"startTime": 10, "stopTime": 5, "stepSize": 0.1},
    })

    assert response.status_code == 400
    assert "stopTime" in response.json()["detail"]


@patch("main._resolve_fmu_path")
def test_run_rejects_zero_step_size(mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {},
        "options": {"startTime": 0, "stopTime": 10, "stepSize": 0},
    })

    assert response.status_code == 400
    assert "stepSize" in response.json()["detail"]


@patch("main._resolve_fmu_path")
def test_run_rejects_non_positive_timeout(mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {},
        "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.1, "timeout": 0},
    })

    assert response.status_code == 400
    assert "timeout" in response.json()["detail"]


@patch("main._resolve_fmu_path")
@patch("main.read_model_description")
@patch("main._executor")
def test_run_times_out_when_exceeding_timeout(mock_exec, mock_md, mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"
    md_obj = MagicMock(); md_obj.coSimulation = True; md_obj.modelExchange = False
    mock_md.return_value = md_obj
    mock_exec.submit.return_value = _make_delayed_future(_make_run_result(), delay_sec=1.5)

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {"mass": 1.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.1, "timeout": 1},
    })

    assert response.status_code == 504
    assert "timed out" in response.json()["detail"]
    # Allow deferred cleanup callback to release the concurrency slot.
    time.sleep(0.7)


def test_run_rejects_non_fmu_resource_type():
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(resourceType="lab")
    try:
        response = client.post("/api/v1/simulations/run", json={
            "labId": "1",
            "parameters": {},
            "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.1},
        })
        assert response.status_code == 403
        assert "FMU endpoints" in response.json()["detail"]
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


def test_run_rejects_missing_access_key():
    """When JWT has no accessKey, should return 400."""
    # Temporarily override with claims missing accessKey
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(accessKey=None)
    try:
        response = client.post("/api/v1/simulations/run", json={
            "labId": "1",
            "parameters": {},
            "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.1},
        })
        assert response.status_code == 400
        assert "FMU file name" in response.json()["detail"]
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


# ─── Concurrency ────────────────────────────────────────────────────


@patch("main._resolve_fmu_path")
def test_run_rejects_lab_id_mismatch(mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(labId="99", accessKey="test.fmu")
    try:
        response = client.post("/api/v1/simulations/run", json={
            "labId": "1",
            "parameters": {},
            "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.1},
        })
        assert response.status_code == 403
        assert "labId" in response.json()["detail"]
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()

@patch("main.MAX_CONCURRENT_PER_MODEL", 0)
@patch("main._resolve_fmu_path")
def test_run_returns_429_when_concurrency_exceeded(mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {},
        "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.1},
    })

    assert response.status_code == 429
    assert "Concurrency limit" in response.json()["detail"]


# ─── #18 — NDJSON Streaming ─────────────────────────────────────────

@patch("main._resolve_fmu_path")
@patch("main._executor")
@patch("main.read_model_description")
def test_stream_returns_ndjson_events(mock_md, mock_exec, mock_resolve):
    mock_resolve.return_value = "/fake/path/spring.fmu"
    mock_md_obj = MagicMock()
    mock_md_obj.coSimulation = True
    mock_md_obj.modelExchange = False
    mock_md.return_value = mock_md_obj
    mock_exec.submit.return_value = _make_future(_make_run_result())

    response = client.post("/api/v1/simulations/stream", json={
        "labId": "1",
        "parameters": {"mass": 1.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.1},
    })

    assert response.status_code == 200
    assert "application/x-ndjson" in response.headers.get("content-type", "")

    lines = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
    types = [l["type"] for l in lines]
    assert "started" in types
    assert "completed" in types
    # At least one data chunk
    assert "data" in types
    # Started message has simId
    started = next(l for l in lines if l["type"] == "started")
    assert "simId" in started


# --- #29 - Simulation History ---
def test_upload_endpoint_removed():
    """FMU upload is intentionally not exposed from Marketplace/Gateway."""
    response = client.post("/api/v1/fmu/upload")
    assert response.status_code == 404


def test_list_fmus_returns_only_provisioned_file(tmp_path, monkeypatch):
    model_file = tmp_path / "provider-1" / "test.fmu"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"dummy")
    monkeypatch.setattr("main.FMU_DATA_PATH", str(tmp_path))
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(accessKey="test.fmu", resourceType="fmu")
    try:
        response = client.get("/api/v1/fmu/list")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["fmus"]) == 1
        assert payload["fmus"][0]["filename"] == "test.fmu"
        assert payload["fmus"][0]["source"] == "provisioned"
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


def test_list_fmus_requires_access_key():
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(accessKey=None, resourceType="fmu")
    try:
        response = client.get("/api/v1/fmu/list")
        assert response.status_code == 403
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_download_generates_fmu_archive(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test.fmu"
    mock_issue_ticket.return_value = ("st_ticket_1", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "linux64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.so").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 200
        assert "application/octet-stream" in response.headers.get("content-type", "")

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(archive.namelist())
        assert "modelDescription.xml" in names
        assert "resources/config.json" in names
        assert "binaries/linux64/decentralabs_proxy.so" in names
        assert all(not name.lower().endswith(".fmu") for name in names)
        assert all("/model/" not in name.lower() for name in names)
        assert all("/sources/" not in name.lower() for name in names)
        assert response.headers.get("x-proxy-artifact-sha256") == hashlib.sha256(response.content).hexdigest()

        config = json.loads(archive.read("resources/config.json").decode("utf-8"))
        assert config["sessionTicket"] == "st_ticket_1"
        assert config["labId"] == "1"
        assert config["reservationKey"] == "0xabc"
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_fmu_is_loadable_by_python_fmi_tools(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test.fmu"
    mock_issue_ticket.return_value = ("st_ticket_1", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "linux64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.so").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 200

        proxy_path = tmp_path / "proxy.fmu"
        proxy_path.write_bytes(response.content)
        md = read_model_description(str(proxy_path))
        assert md.fmiVersion == "2.0"
        assert md.coSimulation is not None
        assert any(var.name == "mass" for var in md.modelVariables)
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockFmi3ModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_download_generates_fmi3_archive_layout(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test-fmi3.fmu"
    mock_issue_ticket.return_value = ("st_ticket_3", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "win64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.dll").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test-fmi3.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 200

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(archive.namelist())
        assert "modelDescription.xml" in names
        assert "resources/config.json" in names
        assert "binaries/x86_64-windows/decentralabs_proxy.dll" in names

        config = json.loads(archive.read("resources/config.json").decode("utf-8"))
        assert config["fmiVersion"] == "3.0"

        proxy_path = tmp_path / "proxy-fmi3.fmu"
        proxy_path.write_bytes(response.content)
        md = read_model_description(str(proxy_path))
        assert md.fmiVersion == "3.0"
        assert md.coSimulation is not None
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockFmi3ModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_model_description_matches_public_describe_payload(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test-fmi3.fmu"
    mock_issue_ticket.return_value = ("st_ticket_3", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "win64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.dll").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test-fmi3.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        describe_response = client.get("/api/v1/simulations/describe?fmuFileName=test-fmi3.fmu")
        assert describe_response.status_code == 200
        describe_payload = describe_response.json()

        proxy_response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert proxy_response.status_code == 200

        archive = zipfile.ZipFile(io.BytesIO(proxy_response.content))
        root = ET.fromstring(archive.read("modelDescription.xml"))
        variables = []
        for child in root.findall("./ModelVariables/*"):
            variables.append({
                "name": child.attrib["name"],
                "type": child.tag,
                "causality": child.attrib.get("causality", "local"),
                "variability": child.attrib.get("variability", "continuous"),
                **({"initial": child.attrib["initial"]} if "initial" in child.attrib else {}),
                **({"start": child.attrib["start"]} if "start" in child.attrib else {}),
            })

        described_variables = {
            item["name"]: {
                "name": item["name"],
                "type": "Int32" if item["type"] == "Integer" else item["type"],
                "causality": item["causality"],
                "variability": item["variability"],
                **({"initial": item["initial"]} if "initial" in item else {}),
                **({"start": str(item["start"])} if "start" in item else {}),
            }
            for item in describe_payload["modelVariables"]
        }
        xml_variables = {item["name"]: item for item in variables}

        assert describe_payload["fmiVersion"] == root.attrib["fmiVersion"]
        assert describe_payload["simulationKind"] == "coSimulation"
        assert set(described_variables.keys()) == set(xml_variables.keys())
        for name, variable in described_variables.items():
            assert xml_variables[name] == variable
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_download_adds_hmac_signature_header(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test.fmu"
    mock_issue_ticket.return_value = ("st_ticket_1", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "linux64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.so").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))
    monkeypatch.setattr("main.FMU_PROXY_SIGNING_KEY", "top-secret")

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 200
        expected_sig = hmac.new(b"top-secret", response.content, hashlib.sha256).hexdigest()
        assert response.headers.get("x-proxy-artifact-signature") == f"hmac-sha256={expected_sig}"
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_download_requires_runtime_binaries(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test.fmu"
    mock_issue_ticket.return_value = ("st_ticket_1", 4102444800)
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(tmp_path / "missing-runtime"))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 503
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main.read_model_description", return_value=MockModelDescription())
@patch("main._issue_session_ticket", new_callable=AsyncMock)
@patch("main._resolve_fmu_path")
def test_proxy_download_rate_limited(mock_resolve, mock_issue_ticket, mock_read_md, tmp_path, monkeypatch):
    mock_resolve.return_value = tmp_path / "test.fmu"
    mock_issue_ticket.return_value = ("st_ticket_1", 4102444800)

    runtime_root = tmp_path / "runtime"
    runtime_bin = runtime_root / "binaries" / "linux64"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    (runtime_bin / "decentralabs_proxy.so").write_bytes(b"binary")
    monkeypatch.setattr("main.FMU_PROXY_RUNTIME_PATH", str(runtime_root))
    monkeypatch.setattr("main.PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr("main._proxy_download_hits", defaultdict(deque))

    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(
        accessKey="test.fmu",
        resourceType="fmu",
        labId="1",
        reservationKey="0xabc",
        aud="https://gateway.example/auth",
    )
    try:
        response = client.get(
            "/api/v1/fmu/proxy/1?reservationKey=0xabc",
            headers={"Authorization": "Bearer booking-token"},
        )
        assert response.status_code == 429
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()

def test_history_empty_initially(tmp_path, monkeypatch):
    monkeypatch.setattr("main.HISTORY_DB_PATH", str(tmp_path / "test.db"))
    # Ensure schema exists
    import asyncio
    asyncio.run(_init_db())

    response = client.get("/api/v1/simulations/history")
    assert response.status_code == 200
    assert response.json()["simulations"] == []


@patch("main._resolve_fmu_path")
@patch("main._executor")
@patch("main.read_model_description")
def test_run_persists_to_history(mock_md, mock_exec, mock_resolve, tmp_path, monkeypatch):
    """After a successful run, the simulation appears in the history endpoint."""
    mock_resolve.return_value = "/fake/path/spring.fmu"
    mock_md_obj = MagicMock()
    mock_md_obj.coSimulation = True
    mock_md_obj.modelExchange = False
    mock_md.return_value = mock_md_obj
    mock_exec.submit.return_value = _make_future(_make_run_result())

    db_path = str(tmp_path / "hist.db")
    monkeypatch.setattr("main.HISTORY_DB_PATH", db_path)
    import asyncio
    asyncio.run(_init_db())

    # Run a simulation
    run_resp = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {"mass": 1.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.1},
    })
    assert run_resp.status_code == 200
    sim_id = run_resp.json()["simId"]

    # Check history
    hist_resp = client.get("/api/v1/simulations/history?labId=1")
    assert hist_resp.status_code == 200
    sims = hist_resp.json()["simulations"]
    assert len(sims) >= 1
    assert sims[0]["id"] == sim_id

    # Retrieve full result
    result_resp = client.get(f"/api/v1/simulations/{sim_id}/result")
    assert result_resp.status_code == 200
    assert "result" in result_resp.json()


# ─── #31 — Model Exchange ───────────────────────────────────────────

class MockModelExchangeDescription:
    """Fake FMPy model description for a ModelExchange-only FMU."""
    fmiVersion = "2.0"
    coSimulation = None
    modelExchange = True

    class defaultExperiment:
        startTime = 0.0
        stopTime = 5.0
        stepSize = 0.001

    class _Var:
        def __init__(self, name, causality, type_, unit=None, start=None):
            self.name = name
            self.causality = causality
            self.type = type_
            self.unit = unit
            self.start = start
            self.min = None
            self.max = None

    modelVariables = [
        _Var("theta", "input", "Real", "rad", 0.0),
        _Var("omega", "output", "Real", "rad/s"),
    ]


@patch("main.read_model_description", return_value=MockModelExchangeDescription())
@patch("main._resolve_fmu_path")
def test_describe_model_exchange(mock_resolve, mock_read):
    mock_resolve.return_value = "/fake/path/pendulum.fmu"
    app.dependency_overrides[_original_verify_jwt] = _fake_jwt(accessKey="pendulum.fmu")
    try:
        response = client.get("/api/v1/simulations/describe?fmuFileName=pendulum.fmu")
        assert response.status_code == 200
        data = response.json()
        assert data["simulationType"] == "ModelExchange"
        assert data["supportsCoSimulation"] is False
        assert data["supportsModelExchange"] is True
    finally:
        app.dependency_overrides[_original_verify_jwt] = _fake_jwt()


@patch("main._resolve_fmu_path")
@patch("main._executor")
@patch("main.read_model_description", return_value=MockModelExchangeDescription())
def test_run_model_exchange_auto_detect(mock_md, mock_exec, mock_resolve):
    """When fmiType is not specified, auto-detect from model description."""
    mock_resolve.return_value = "/fake/path/pendulum.fmu"
    mock_exec.submit.return_value = _make_future(_make_run_result("ModelExchange"))

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {"theta": 0.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.01},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["fmiType"] == "ModelExchange"
    # Verify _run_simulation was called with ModelExchange fmi_type
    call_args = mock_exec.submit.call_args
    # positional args: _run_simulation, fmu_path, start, stop, step, params, timeout, fmi_type, solver
    assert call_args[0][7] == "ModelExchange"


@patch("main._resolve_fmu_path")
@patch("main._executor")
@patch("main.read_model_description", return_value=MockModelExchangeDescription())
def test_run_explicit_fmi_type_and_solver(mock_md, mock_exec, mock_resolve):
    """Client can explicitly set fmiType and solver in options."""
    mock_resolve.return_value = "/fake/path/pendulum.fmu"
    mock_exec.submit.return_value = _make_future(_make_run_result("ModelExchange"))

    response = client.post("/api/v1/simulations/run", json={
        "labId": "1",
        "parameters": {},
        "options": {
            "startTime": 0, "stopTime": 1, "stepSize": 0.01,
            "fmiType": "ModelExchange", "solver": "CVode",
        },
    })
    assert response.status_code == 200
    assert response.json()["fmiType"] == "ModelExchange"






