"""The downloadable proxy must carry usable, bounded FMI companion resources."""

from copy import deepcopy
import csv
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

import proxy_artifact as artifact


MODEL = b'''<fmiModelDescription fmiVersion="3.0"><ModelVariables>
<Boolean name="enableDAE" valueReference="1"/><Float64 name="x" valueReference="2"/>
<Float64 name="residual" valueReference="3"/></ModelVariables></fmiModelDescription>'''


def _build(**options):
    return artifact.build_proxy_artifact(model_xml=MODEL, config_payload={"sessionTicket": "ticket"}, runtime_files=[], **options)


def _files(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def _metadata():
    return {"modelVariables": [
        {"name": "gain", "type": "Float64"}, {"name": "enabled", "type": "Boolean"},
        {"name": "labels", "type": "String"},
        {"name": "mode", "type": "Enumeration", "enumItems": [None, {"name": "off", "value": 0}, {"name": "on", "value": 1}]},
        {"name": "opaque", "type": "Binary"},
        {"name": "enableDAE", "type": "Boolean", "valueReference": 1},
    ]}


def test_proxy_presets_and_experiments_round_trip_arrays_enumerations_and_csv_stimuli():
    files = _files(_build(
        fmi_ls_model_metadata=_metadata(),
        fmi_ls_parameter_sets=[{"name": "Initial", "description": "Preset", "parameters": {
            "gain": [1.25, 2], "enabled": False, "labels": ["a<&", "b"], "mode": [0, 1],
        }}],
        fmi_ls_experiments=[{"name": "Step", "description": "Response", "parameters": {"gain": 3},
            "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.5},
            "inputSchedule": [{"time": 0, "values": {"input,1": 2, "u": 3}},
                              {"time": 0.5, "values": {"input,1": 4, "u": 5}}]}],
    ))
    prefix = "extra/org.fmi-standard.fmi-ls-ref/"
    parameter_xml = ET.fromstring(files[prefix + "parameters/configuration-1.ssv"])
    params = {p.attrib["name"]: p for p in parameter_xml.find("{*}Parameters")}
    assert params["enabled"].find("{*}Boolean").attrib["value"] == "false"
    assert params["gain"].find("{*}Dimension").attrib["size"] == "2"
    assert [x.text for x in params["labels"].find("{*}String")] == ["a<&", "b"]
    assert [x.text for x in params["mode"].find("{*}Enumeration")] == ["off", "on"]
    rows = list(csv.reader(io.StringIO(files[prefix + "experiments/stimuli/experiment-1.csv"].decode())))
    assert rows == [["time", "input,1", "u"], ["0", "2", "3"], ["0.5", "4", "5"]]
    experiments = ET.fromstring(files[prefix + "experiments/provider-experiments.exp"])
    case = experiments.find("{*}TransientExperiment")
    assert case.attrib["stopTime"] == "1"
    assert case.find("{*}Parameters").attrib["source"] == "../parameters/experiment-1.ssv"
    assert case.find("{*}Stimuli").attrib["source"] == "stimuli/experiment-1.csv"
    assert json.loads(files["resources/config.json"]) == {"sessionTicket": "ticket"}


@pytest.mark.parametrize("parameters", [None, {}, {"missing": 1}, {"opaque": "data"},
                                       {"mode": 99}, {"gain": []}, {"gain": [0] * 4097},
                                       {"gain": float("nan")}, {"gain": {"nested": 1}}])
def test_unrenderable_presets_do_not_leave_partial_ref_resources(parameters):
    files = _files(_build(fmi_ls_model_metadata=_metadata(), fmi_ls_parameter_sets=[None, {"parameters": parameters}]))
    assert not any(name.startswith("extra/") for name in files)


@pytest.mark.parametrize("schedule", [
    [None], [{"time": 0, "values": {}}], [{"time": 0, "values": {1: 2}}],
    [{"time": 0, "values": {"u": 1}}, {"time": 1, "values": {"v": 2}}],
    [{"time": float("inf"), "values": {"u": 1}}], [{"time": 0, "values": {"u": None}}],
])
def test_unrenderable_experiments_are_omitted_atomically(schedule):
    files = _files(_build(fmi_ls_model_metadata=_metadata(), fmi_ls_experiments=[{
        "name": "Invalid", "parameters": {"gain": 1}, "options": {"stopTime": 1}, "inputSchedule": schedule,
    }]))
    assert not any(name.startswith("extra/") for name in files)


def _dae():
    return {"manifestName": "org.fmi-standard.fmi-ls-dae", "manifestVersion": "1.0.0-alpha.1",
            "enableDAEParameter": "enableDAE", "algebraicValueReferences": [2], "residualVariables": [],
            "modelStructure": {"residuals": [{"valueReference": 3, "dependencies": [2], "dependenciesKind": ["dependent"]}]}}


def test_proxy_dae_manifest_preserves_selector_and_model_structure_references():
    files = _files(_build(fmi_ls_dae=_dae(), fmi_ls_model_metadata=_metadata()))
    root = ET.fromstring(files["extra/org.fmi-standard.fmi-ls-dae/fmi-ls-manifest.xml"])
    assert root.find("EnableDAEParameter").attrib == {"valueReference": "1"}
    assert root.find("AlgebraicVariables/AlgebraicVariable").attrib == {"valueReference": "2"}
    assert root.find("ModelStructure/Residual").attrib == {"valueReference": "3", "dependencies": "2", "dependenciesKind": "dependent"}


@pytest.mark.parametrize("field,value", [
    ("manifestName", "other"), ("manifestVersion", "other"), ("enableDAEParameter", "missing"),
    ("algebraicValueReferences", None), ("algebraicValueReferences", [True]),
    ("algebraicValueReferences", [-1]), ("residualVariables", None), ("modelStructure", []),
    ("modelStructure", {"outputs": {}}), ("modelStructure", {"outputs": [None]}),
    ("modelStructure", {"outputs": [{"valueReference": True}]}),
    ("modelStructure", {"outputs": [{"valueReference": 2, "dependencies": [True]}]}),
    ("modelStructure", {"outputs": [{"valueReference": 2, "dependenciesKind": [1]}]}),
])
def test_invalid_dae_metadata_cannot_be_serialized_into_a_download(field, value):
    dae = deepcopy(_dae())
    dae[field] = value
    with pytest.raises(ValueError):
        _build(fmi_ls_dae=dae, fmi_ls_model_metadata=_metadata())


def test_ref_budget_rejection_never_returns_a_partial_archive(monkeypatch):
    monkeypatch.setattr(artifact, "_MAX_FMI_LS_REF_BUNDLE_BYTES", 10)
    with pytest.raises(artifact.ProxyFmiLsRefSizeLimitError, match="size limit"):
        _build(fmi_ls_model_metadata=_metadata(), fmi_ls_parameter_sets=[{"parameters": {"gain": 1}}])


def test_parameter_and_stimulus_file_budgets_are_enforced(monkeypatch):
    monkeypatch.setattr(artifact, "_MAX_FMI_LS_REF_PARAMETER_FILE_BYTES", 1)
    files = _files(_build(fmi_ls_model_metadata=_metadata(), fmi_ls_parameter_sets=[{"parameters": {"gain": 1}}]))
    assert not any(name.startswith("extra/") for name in files)
    monkeypatch.setattr(artifact, "_MAX_FMI_LS_REF_STIMULI_FILE_BYTES", 1)
    files = _files(_build(fmi_ls_model_metadata=_metadata(), fmi_ls_experiments=[{
        "parameters": {}, "options": {"stopTime": 1}, "inputSchedule": [{"time": 0, "values": {"u": 1}}],
    }]))
    assert not any(name.startswith("extra/") for name in files)
