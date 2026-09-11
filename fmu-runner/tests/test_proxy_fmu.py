from xml.etree import ElementTree as ET

from proxy_fmu import _build_proxy_model_description_xml, _collect_runtime_files


def test_proxy_fmu_module_generates_model_description_without_main_import():
    xml_bytes = _build_proxy_model_description_xml({
        "modelName": "ProxyBoundary",
        "guid": "{proxy-guid}",
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "modelVariables": [],
    })

    root = ET.fromstring(xml_bytes)

    assert root.attrib["modelName"] == "ProxyBoundary"
    assert root.attrib["fmiVersion"] == "3.0"
    assert root.find("./CoSimulation").attrib["modelIdentifier"] == "decentralabs_proxy"


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