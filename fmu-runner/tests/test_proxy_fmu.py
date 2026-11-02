from xml.etree import ElementTree as ET

from proxy_fmu import _build_proxy_model_description_xml, _collect_runtime_files


def _validate_model_description(xml_bytes: bytes, fmi_version: str) -> None:
    from pathlib import Path

    from fmpy import __file__ as fmpy_init
    import lxml.etree as etree

    major = fmi_version.split(".", 1)[0]
    schema_path = Path(fmpy_init).parent / "schema" / f"fmi{major}" / f"fmi{major}ModelDescription.xsd"
    schema = etree.XMLSchema(etree.parse(str(schema_path)))
    document = etree.fromstring(xml_bytes)
    assert schema.validate(document), str(schema.error_log)


def test_proxy_fmu_module_generates_model_description_without_main_import():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyBoundary",
        "guid": "{proxy-guid}",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [],
    })

    root = ET.fromstring(xml_bytes)
    co_simulation = root.find("./CoSimulation")
    assert co_simulation is not None

    assert root.attrib["modelName"] == "ProxyBoundary"
    assert root.attrib["fmiVersion"] == "3.0"
    assert co_simulation.attrib["modelIdentifier"] == "decentralabs_proxy"


def test_fmi3_cosimulation_uses_standard_early_return_attribute_and_xsd():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyBoundary",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [{
            "name": "output",
            "valueReference": 1,
            "type": "Float64",
            "causality": "output",
            "variability": "continuous",
        }],
    })

    root = ET.fromstring(xml_bytes)
    co_simulation = root.find("./CoSimulation")
    assert co_simulation is not None
    assert co_simulation.attrib["mightReturnEarlyFromDoStep"] == "true"
    assert "mightReturnEarly" not in co_simulation.attrib
    _validate_model_description(xml_bytes, "3.0")


def test_fmi3_string_and_binary_array_starts_emit_one_child_per_value():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyArrays",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [
            {
                "name": "labels",
                "valueReference": 1,
                "type": "String",
                "causality": "parameter",
                "variability": "fixed",
                "dimensions": [{"start": 2}],
                "start": ["north", "south"],
            },
            {
                "name": "payloads",
                "valueReference": 2,
                "type": "Binary",
                "causality": "parameter",
                "variability": "fixed",
                "dimensions": [{"start": 2}],
                "start": ["AQI=", "AwQ="],
            },
        ],
    })

    root = ET.fromstring(xml_bytes)
    labels = root.find("./ModelVariables/String[@name='labels']")
    payloads = root.find("./ModelVariables/Binary[@name='payloads']")
    assert labels is not None
    assert payloads is not None
    assert [item.attrib["value"] for item in labels.findall("./Start")] == ["north", "south"]
    assert [item.attrib["value"] for item in payloads.findall("./Start")] == ["0102", "0304"]
    _validate_model_description(xml_bytes, "3.0")


def test_proxy_fmu_module_selects_fmi3_runtime_binary_layout(tmp_path):
    runtime_binary = tmp_path / "binaries" / "win64" / "decentralabs_proxy.dll"
    runtime_binary.parent.mkdir(parents=True)
    runtime_binary.write_bytes(b"binary")

    files = _collect_runtime_files(
        runtime_path=tmp_path,
        fmi_version="3.0",
        model_identifier="decentralabs_proxy",
    )

    assert files == [(runtime_binary, "binaries/x86_64-windows/decentralabs_proxy.dll")]
