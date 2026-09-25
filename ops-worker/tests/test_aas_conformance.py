"""Strict AAS/AASX conformance tests for generated physical-lab resources."""

import io
import json
from pathlib import Path

from basyx.aas.adapter.aasx import (
    AASXReader,
    AASXWriter,
    DictSupplementaryFileContainer,
)
from basyx.aas.adapter.json import read_aas_json_file

import aas_generator as generator


HOST = {
    "name": "lab-ws-01",
    "address": "192.168.1.100",
    "mac": "00:11:22:33:44:55",
}

HEARTBEAT = {
    "timestamp": "2026-01-01T12:00:00.000Z",
    "summary": {"ready": True},
    "status": {"localModeEnabled": False, "localSessionActive": False},
    "operations": {
        "lastForcedLogoff": {"timestamp": "2025-12-31T10:00:00Z", "user": "student1"},
        "lastPowerAction": {"timestamp": "2026-01-01T08:00:00Z", "mode": "powerOn"},
    },
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


def test_generated_physical_lab_environment_is_strictly_readable_in_basyx():
    extra_info = {
        "contactEmail": "lab@example.test",
        "documentationUrls": ["https://example.test/manual.pdf"],
    }
    shell = generator.build_physical_aas_shell("42", HOST, extra_info)
    submodels = [
        generator.build_nameplate_submodel("42", HOST, extra_info),
        generator.build_technical_data_submodel("42", HOST, HEARTBEAT),
        generator.build_execution_capabilities_submodel("42", HOST, HEARTBEAT),
        generator.build_asset_interfaces_description_submodel(
            "42",
            [("ReadOperationalStatus", "/health", "GET", "")],
        ),
        generator.build_contact_information_submodel("42", extra_info),
        generator.build_handover_documentation_submodel("42", extra_info),
    ]

    store = _strict_json_store(shell, [submodel for submodel in submodels if submodel is not None])
    assert len(store) == 7


def test_generated_physical_lab_aasx_round_trip_is_strictly_readable(tmp_path):
    shell = generator.build_physical_aas_shell("42", HOST)
    submodels = [
        generator.build_nameplate_submodel("42", HOST),
        generator.build_technical_data_submodel("42", HOST, None),
        generator.build_execution_capabilities_submodel("42", HOST, None),
        generator.build_asset_interfaces_description_submodel(
            "42",
            [("ReadOperationalStatus", "/health", "GET", "")],
        ),
    ]
    object_store = _strict_json_store(shell, submodels)
    package_path = Path(tmp_path) / "physical-lab.aasx"

    with AASXWriter(package_path) as writer:
        writer.write_aas(
            shell["id"],
            object_store,
            DictSupplementaryFileContainer(),
            write_json=False,
        )

    with AASXReader(package_path, failsafe=False) as reader:
        parsed_ids = reader.read_into(
            type(object_store)(),
            DictSupplementaryFileContainer(),
        )

    assert shell["id"] in parsed_ids
    assert {submodel["id"] for submodel in submodels}.issubset(parsed_ids)
