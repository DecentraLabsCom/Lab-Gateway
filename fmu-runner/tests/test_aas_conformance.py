"""Strict AAS/AASX conformance tests for generated FMU resources.

The local payload checks are useful for fast feedback, but they do not exercise
the XML/AASX codecs.  Eclipse BaSyx's Python SDK is the independent parser used
here with ``failsafe=False`` so malformed mandatory fields fail the test.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from basyx.aas.adapter.aasx import (
    AASXReader,
    AASXWriter,
    DictSupplementaryFileContainer,
)
from basyx.aas.adapter.json import read_aas_json_file

from aas_generator import (
    build_aas_shell,
    build_asset_interfaces_description_submodel,
    build_contact_information_submodel,
    build_execution_capabilities_submodel,
    build_handover_documentation_submodel,
    build_simulation_submodel,
    build_technical_data_submodel,
)


def _metadata() -> dict:
    return {
        "modelName": "ConformanceTestModel",
        "fmiVersion": "3.0",
        "simulationType": "CoSimulation",
        "supportsCoSimulation": True,
        "defaultStartTime": 0.0,
        "defaultStopTime": 10.0,
        "modelVariables": [
            {"name": "force", "causality": "input", "type": "Real", "unit": "N", "start": 0.0},
            {"name": "velocity", "causality": "output", "type": "Real"},
        ],
    }


def _strict_json_store(shell: dict, submodels: list[dict]):
    environment = {
        "assetAdministrationShells": [shell],
        "submodels": submodels,
    }
    return read_aas_json_file(
        io.StringIO(json.dumps(environment)),
        failsafe=False,
    )


def _round_trip_aasx(
    tmp_path: Path,
    shell: dict,
    submodels: list[dict],
    supplementary_files: DictSupplementaryFileContainer,
) -> None:
    object_store = _strict_json_store(shell, submodels)
    package_path = tmp_path / "generated.aasx"

    with AASXWriter(package_path) as writer:
        writer.write_aas(shell["id"], object_store, supplementary_files, write_json=False)

    with AASXReader(package_path, failsafe=False) as reader:
        parsed_ids = reader.read_into(
            type(object_store)(),
            DictSupplementaryFileContainer(),
        )

    assert shell["id"] in parsed_ids
    assert {submodel["id"] for submodel in submodels}.issubset(parsed_ids)


def test_generated_fmu_environment_is_strictly_readable_in_basyx():
    metadata = _metadata()
    extra_info = {
        "contactEmail": "lab@example.test",
        "documentationUrls": ["https://example.test/manual.pdf"],
    }
    shell = build_aas_shell("42", "test.fmu", metadata, extra_info)
    submodels = [
        build_simulation_submodel("42", "test.fmu", metadata, extra_info),
        build_technical_data_submodel("42", metadata),
        build_execution_capabilities_submodel("42", metadata),
        build_asset_interfaces_description_submodel(
            "42",
            [("RunSimulation", "/fmu/api/v1/simulations/run", "POST", "")],
        ),
        build_contact_information_submodel("42", extra_info),
        build_handover_documentation_submodel("42", extra_info),
    ]

    store = _strict_json_store(shell, [submodel for submodel in submodels if submodel is not None])
    assert len(store) == 7


def test_generated_fmu_aasx_round_trip_is_strictly_readable(tmp_path):
    metadata = _metadata()
    shell = build_aas_shell("42", "test.fmu", metadata)
    submodels = [
        build_simulation_submodel("42", "test.fmu", metadata),
        build_technical_data_submodel("42", metadata),
        build_execution_capabilities_submodel("42", metadata),
        build_asset_interfaces_description_submodel(
            "42",
            [("RunSimulation", "/fmu/api/v1/simulations/run", "POST", "")],
        ),
    ]
    files = DictSupplementaryFileContainer()
    files.add_file("/fmu-data/test.fmu", io.BytesIO(b"test-fmu"), "application/zip")

    _round_trip_aasx(tmp_path, shell, submodels, files)


def test_basyx_strict_reader_rejects_aasx_without_list_element_type(tmp_path):
    metadata = _metadata()
    shell = build_aas_shell("42", "test.fmu", metadata)
    submodels = [
        build_simulation_submodel("42", "test.fmu", metadata),
        build_technical_data_submodel("42", metadata),
        build_execution_capabilities_submodel("42", metadata),
        build_asset_interfaces_description_submodel(
            "42",
            [("RunSimulation", "/fmu/api/v1/simulations/run", "POST", "")],
        ),
    ]
    files = DictSupplementaryFileContainer()
    files.add_file("/fmu-data/test.fmu", io.BytesIO(b"test-fmu"), "application/zip")
    valid_path = tmp_path / "valid.aasx"
    invalid_path = tmp_path / "invalid.aasx"
    object_store = _strict_json_store(shell, submodels)

    with AASXWriter(valid_path) as writer:
        writer.write_aas(shell["id"], object_store, files, write_json=False)

    with zipfile.ZipFile(valid_path) as source, zipfile.ZipFile(invalid_path, "w") as target:
        for part in source.infolist():
            content = source.read(part.filename)
            if part.filename.endswith(".xml"):
                content = content.replace(
                    b"<aas:typeValueListElement>SubmodelElementCollection</aas:typeValueListElement>",
                    b"",
                    1,
                )
            target.writestr(part, content)

    with pytest.raises(KeyError):
        with AASXReader(invalid_path, failsafe=False) as reader:
            reader.read_into(type(object_store)(), DictSupplementaryFileContainer())
