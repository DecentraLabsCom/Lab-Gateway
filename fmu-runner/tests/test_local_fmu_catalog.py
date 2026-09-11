import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from local_fmu_catalog import (
    _list_local_fmus_payload,
    _load_local_model_metadata,
    _local_backend_health_payload,
)


def test_local_backend_health_counts_fmus_and_executor_state(tmp_path):
    (tmp_path / "provider-1").mkdir()
    (tmp_path / "provider-1" / "model.fmu").write_bytes(b"fmu")

    payload = _local_backend_health_payload(
        data_path=tmp_path,
        executor=SimpleNamespace(_broken=False),
    )

    assert payload == {
        "status": "UP",
        "checks": {"fmuDataPath": True, "executor": True},
        "fmuCount": 1,
        "backendMode": "local",
    }


def test_list_local_fmus_payload_returns_provisioned_file_details(tmp_path):
    fmu_path = tmp_path / "provider-1" / "model.fmu"
    fmu_path.parent.mkdir()
    fmu_path.write_bytes(b"fmu")

    payload = _list_local_fmus_payload(
        "model.fmu",
        data_path=tmp_path,
        resolve_fmu_path=lambda _filename: fmu_path,
        is_within_base=lambda _base, _candidate: True,
    )

    assert payload == {
        "fmus": [{
            "filename": "model.fmu",
            "path": "provider-1\\model.fmu",
            "sizeBytes": 3,
            "source": "provisioned",
        }]
    }


def test_load_local_model_metadata_translates_parser_errors():
    logger = logging.getLogger("test-local-fmu-catalog")

    def failing_reader(_path):
        raise ValueError("invalid model description")

    with pytest.raises(HTTPException) as error:
        _load_local_model_metadata(
            "model.fmu",
            resolve_fmu_path=lambda _filename: "C:/model.fmu",
            model_description_reader=failing_reader,
            model_metadata_builder=lambda model_description: model_description,
            logger=logger,
        )

    assert error.value.status_code == 422
    assert error.value.detail == "Cannot parse FMU"


def test_load_local_model_metadata_builds_public_metadata():
    model_description = SimpleNamespace(modelName="ThermalModel")

    metadata = _load_local_model_metadata(
        "model.fmu",
        resolve_fmu_path=lambda _filename: "C:/model.fmu",
        model_description_reader=lambda _path: model_description,
        model_metadata_builder=lambda parsed: {"modelName": parsed.modelName},
        logger=logging.getLogger("test-local-fmu-catalog"),
    )

    assert metadata == {"modelName": "ThermalModel"}