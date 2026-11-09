"""FMI metadata omitted by the native parser must survive the XML fallback."""

import base64
from types import SimpleNamespace as NS
import zipfile

import pytest

import metadata


def _archive(tmp_path, xml):
    path = tmp_path / "model.fmu"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("modelDescription.xml", xml)
    return path


@pytest.mark.parametrize("fmi_version", ["2.0", "3.0"])
def test_xml_fallback_restores_declared_types_and_explicit_variable_overrides(tmp_path, fmi_version):
    real_type = '<Float64Type name="Temperature" description="Temperature type" unit="K" displayUnit="C" quantity="temperature" min="0" max="1000" nominal="300" relativeQuantity="true" unbounded="true"/>'
    real_variable = '<Float64 name="temperature" declaredType="Temperature" relativeQuantity="false" unbounded="false" causality="output" variability="continuous" initial="exact" reinit="true" description="Measured value" min="10"><Alias name="alias" description="Alternative name" displayUnit="C"/><Alias/></Float64>'
    if fmi_version == "2.0":
        real_type = '<SimpleType name="Temperature" description="Temperature type"><Real unit="K" displayUnit="C" quantity="temperature" min="0" max="1000" nominal="300" relativeQuantity="true" unbounded="true"/></SimpleType>'
        real_variable = '<ScalarVariable name="temperature" causality="output" variability="continuous" initial="exact" description="Measured value"><Real declaredType="Temperature" relativeQuantity="false" unbounded="false" reinit="true" min="10"><Alias name="alias" description="Alternative name" displayUnit="C"/></Real></ScalarVariable>'
    path = _archive(tmp_path, f'''<fmiModelDescription fmiVersion="{fmi_version}">
      <TypeDefinitions>{real_type}<SimpleType name="empty"/>
        <EnumerationType name="Mode"><Item name="off" value="0" description="Off"/><Item name="on" value="9007199254740993"/><Item/><Item name="missingValue"/></EnumerationType>
        <ClockType name="Tick" intervalVariability="tunable" intervalDecimal="0.5" shiftDecimal="0" supportsFraction="true" canBeDeactivated="false" resolution="100" intervalCounter="50" shiftCounter="0" priority="0" maxSize="10" mimeType="application/octet-stream"/>
        <Float64Type/><Float64Type name="BadNumbers" min="NaN" max="bad" maxSize="-1" nominal="inf"/>
      </TypeDefinitions>
      <ModelVariables>{real_variable}<Clock name="clock" declaredType="Tick"/>
        <Enumeration name="mode" declaredType="Mode"/><ScalarVariable name="empty"/>
      </ModelVariables>
    </fmiModelDescription>''')
    payload = {
        "typeDefinitions": [{"name": "Temperature", "retained": "parser field"}, {"name": "Unreferenced", "type": "String"}, None],
        "unitDefinitions": [{"name": "K", "displayUnits": [{"name": "C", "factor": 1, "offset": -273.15}]}],
        "modelVariables": [None, {"name": "temperature", "type": "Float64"}, {"name": "clock", "type": "Clock"},
                           {"name": "mode", "type": "Enumeration"}, {"name": "unknown", "type": "Float64"}],
    }
    result = metadata._merge_raw_fmi_type_metadata(payload, path)
    temperature, clock, mode = result["modelVariables"][1:4]
    assert temperature["description"] == "Measured value"
    assert temperature["initial"] == "exact"
    assert temperature["reinit"] is True
    assert temperature["relativeQuantity"] is False
    assert temperature["unbounded"] is False
    assert temperature["min"] == 10.0
    assert temperature["max"] == 1000.0
    assert temperature["nominal"] == 300.0
    assert temperature["declaredType"]["retained"] == "parser field"
    assert temperature["displayUnit"] == {"name": "C", "factor": 1.0, "offset": -273.15}
    assert temperature["aliases"] == [{"name": "alias", "description": "Alternative name", "displayUnit": "C"}]
    assert clock["supportsFraction"] is True
    assert clock["canBeDeactivated"] is False
    assert clock["intervalDecimal"] == 0.5
    assert clock["resolution"] == 100
    assert mode["declaredType"]["items"][1]["value"] == "9007199254740993"
    assert any(item["name"] == "Unreferenced" for item in result["typeDefinitions"])


@pytest.mark.parametrize("xml", [b"not xml", b"<broken>", b"<fmiModelDescription/>"])
def test_incomplete_xml_fallback_does_not_destroy_parser_metadata(tmp_path, xml):
    payload = {"modelVariables": [{"name": "x", "type": "Real"}]}
    assert metadata._merge_raw_fmi_type_metadata(payload, _archive(tmp_path, xml)) == payload


def test_missing_corrupt_and_oversized_archives_do_not_supply_fallback_metadata(tmp_path, monkeypatch):
    assert metadata._read_model_description_xml(tmp_path / "missing.fmu") is None
    bad = tmp_path / "bad.fmu"
    bad.write_bytes(b"not a ZIP")
    assert metadata._read_model_description_xml(bad) is None
    monkeypatch.setattr(metadata, "_MAX_MODEL_DESCRIPTION_XML_BYTES", 20)
    assert metadata._read_model_description_xml(_archive(tmp_path, "<model>" + "x" * 30 + "</model>")) is None


def test_inverse_display_units_are_read_from_the_archive_without_affecting_normal_units(tmp_path):
    path = _archive(tmp_path, '''<fmiModelDescription><UnitDefinitions>
      <Unit name="s"><DisplayUnit name="Hz" inverse="true"/><DisplayUnit name="ms" factor="1000"/><DisplayUnit inverse="true"/></Unit>
      <Unit><DisplayUnit name="ignored" inverse="true"/></Unit>
    </UnitDefinitions></fmiModelDescription>''')
    assert metadata._display_unit_inverse_map_from_fmu(path) == {("s", "Hz"): True}
    assert metadata._display_unit_inverse_map_from_fmu(tmp_path / "missing.fmu") is None
    assert metadata._display_unit_inverse_map_from_fmu(_archive(tmp_path, "<fmiModelDescription/>")) == {}


@pytest.mark.parametrize("fmi_version,relative,expected", [
    ("1.0", False, {"name": "display", "factor": 0.5, "offset": -5.0}),
    ("2.0", False, {"name": "display", "factor": 2.0, "offset": 10.0}),
    ("3.0", True, {"name": "display", "factor": 2.0, "offset": 0.0}),
])
def test_display_unit_conversion_obeys_fmi_version_and_relative_quantities(fmi_version, relative, expected):
    md = NS(fmiVersion=fmi_version, unitDefinitions=[NS(name="base", displayUnits=[NS(name="display", factor=2, offset=10, inverse=False)])])
    assert metadata._display_unit_metadata(md, NS(unit="base", displayUnit="display", relativeQuantity=relative), None) == expected


@pytest.mark.parametrize("factor,offset,inverse", [(0, 0, False), ("bad", 0, False), (float("inf"), 0, False), (1, float("nan"), False), (1, 2, True)])
def test_invalid_display_unit_conversions_are_not_advertised(factor, offset, inverse):
    md = NS(fmiVersion="3.0", unitDefinitions=[NS(name="s", displayUnits=[NS(name="Hz", factor=factor, offset=offset, inverse=inverse)])])
    assert metadata._display_unit_metadata(md, NS(unit="s", displayUnit="Hz"), None) is None


def _variable(name, kind, reference, **values):
    return NS(name=name, type=kind, valueReference=reference, causality="output", variability="discrete", **values)


def test_parser_metadata_keeps_binary_clocks_declared_enumerations_and_model_structure():
    mode_type = NS(name="Mode", type="Enumeration", description="Operating mode", min=-2, max=2**60,
                   items=[NS(name="idle", value=0, description="Idle"), NS(name="run", value=2**60), NS(name="bad", value="invalid")])
    clock_type = NS(name="Tick", type="Clock", intervalVariability="tunable", intervalDecimal=0.5,
                    shiftDecimal=0, supportsFraction=True, canBeDeactivated=False, resolution=100,
                    intervalCounter=50, shiftCounter=0, priority=0, maxSize=64, mimeType="application/octet-stream",
                    relativeQuantity=False, unbounded=False, nominal=1, unit="s", quantity="time")
    state = _variable("x", "Float64", 1, start=[1.0, 2.0])
    derivative = _variable("der_x", "Float64", 2, derivative=state)
    mode = _variable("mode", "Enumeration", 3, declaredType=mode_type, start=2**60,
                     alias=NS(name="original"), displayName=" Mode ")
    clock = _variable("tick", "Clock", 4, declaredType=clock_type, initial="exact", reinit=False,
                      aliases=[NS(name=""), NS(name="clockAlias", description="Alias", displayUnit="s")],
                      dimensions=[NS(start=3, valueReference=8, variable=NS(name="count"))])
    binary = _variable("packet", "Binary", 5, start=b"\0\xff", mimeType="application/octet-stream", maxSize=256)
    unknown = NS(variable=derivative, dependencies=[state, NS(valueReference=True)], dependenciesKind=["dependent"])
    md = NS(fmiVersion="3.0", modelName="Mixed", instantiationToken="token", modelVariables=[state, derivative, mode, clock, binary],
            coSimulation=NS(canGetAndSetFMUstate=True, canSerializeFMUstate=False, maxOutputDerivativeOrder=2,
                            recommendedIntermediateInputSmoothness=0, fixedInternalStepSize=0.5),
            modelExchange=NS(completedIntegratorStepNotNeeded=False, providesAdjointDerivatives=True),
            defaultExperiment=NS(startTime=0, stopTime=5, stepSize=0.5, tolerance=1e-5),
            derivatives=[unknown, NS(variable=NS(valueReference=-1))], outputs=[NS(variable=mode)],
            unitDefinitions=[NS(name="s", baseUnit=NS(s=1, factor=2, offset=1), displayUnits=[NS(name="Hz", factor=2, offset=0)])],
            typeDefinitions=[mode_type, clock_type, NS(name="missing-kind")])
    result = metadata._model_metadata_from_model_description(md, display_unit_inverses={("s", "Hz"): True})
    variables = {v["name"]: v for v in result["modelVariables"]}
    assert variables["mode"]["start"] == str(2**60)
    assert variables["mode"]["aliasOf"] == "original"
    assert variables["mode"]["enumItems"] == [{"name": "idle", "value": 0, "description": "Idle"}, {"name": "run", "value": 2**60}]
    assert variables["packet"]["start"] == base64.b64encode(b"\0\xff").decode()
    assert variables["tick"]["intervalCounter"] == 50
    assert result["modelStructure"]["derivatives"] == [{"valueReference": 2, "name": "der_x", "stateValueReference": 1,
        "stateName": "x", "dependencies": [1], "dependencyNames": ["x"], "dependenciesKind": ["dependent"]}]
    assert result["modelExchangeCapabilities"]["providesAdjointDerivatives"] is True
    assert result["unitDefinitions"][0]["displayUnits"][0]["inverse"] is True
    assert result["defaultTolerance"] == 1e-5
    assert result["capabilities"]["fixedInternalStepSize"] == 0.5
