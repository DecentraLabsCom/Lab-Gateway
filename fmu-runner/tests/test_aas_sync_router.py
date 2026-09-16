from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aas_sync_router import create_aas_sync_router


def _client(*, metadata=None, sync_result=None):
    resolve_fmu_path = MagicMock(return_value=Path("/trusted/demo.fmu"))
    read_model_description = MagicMock(return_value=SimpleNamespace(description="Embedded", license="MIT"))
    metadata_builder = MagicMock(return_value=metadata or {"description": "Embedded", "license": "MIT", "unitDefinitions": []})
    sync_fmu_to_basyx = AsyncMock(return_value=sync_result or {"synced": True})
    logger = MagicMock()
    app = FastAPI()
    app.include_router(create_aas_sync_router(
        resolve_fmu_path=resolve_fmu_path,
        read_model_description=read_model_description,
        metadata_builder=metadata_builder,
        sync_fmu_to_basyx=sync_fmu_to_basyx,
        logger=logger,
    ))
    return TestClient(app), resolve_fmu_path, read_model_description, metadata_builder, sync_fmu_to_basyx


def test_sync_route_builds_metadata_and_preserves_query_fields():
    client, resolve_fmu_path, read_model_description, metadata_builder, sync_fmu_to_basyx = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync?labId=42&description=Override&documentationUrls=%5B%22https%3A%2F%2Fdocs.example.com%2Fmanual.pdf%22%2C%22https%3A%2F%2Fdocs.example.com%2Fguide.html%22%5D&contactEmail=lab%40example.com",
    )

    assert response.status_code == 200
    assert response.json() == {"synced": True}
    resolve_fmu_path.assert_called_once_with("demo.fmu")
    read_model_description.assert_called_once_with(str(Path("/trusted/demo.fmu")))
    metadata_builder.assert_called_once()
    sync_fmu_to_basyx.assert_awaited_once_with(
        lab_id="42",
        access_key="demo.fmu",
        metadata={"description": "Embedded", "license": "MIT", "unitDefinitions": []},
        aasx_bytes=None,
        extra_info={
            "description": "Override",
            "license": "MIT",
            "documentationUrls": [
                "https://docs.example.com/manual.pdf",
                "https://docs.example.com/guide.html",
            ],
            "contactEmail": "lab@example.com",
        },
        fmu_path=Path("/trusted/demo.fmu"),
        unit_definitions=[],
    )


def test_sync_route_accepts_multipart_aasx_without_reading_fmu_metadata():
    client, resolve_fmu_path, read_model_description, _, sync_fmu_to_basyx = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        data={"labId": "99"},
        files={"file": ("demo.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    resolve_fmu_path.assert_not_called()
    read_model_description.assert_not_called()
    assert sync_fmu_to_basyx.await_args.kwargs["lab_id"] == "99"
    assert sync_fmu_to_basyx.await_args.kwargs["aasx_bytes"] == b"aasx-bytes"


def test_generic_resource_route_accepts_physical_lab_aasx_without_reading_fmu_metadata():
    client, resolve_fmu_path, read_model_description, _, sync_fmu_to_basyx = _client()

    response = client.post(
        "/aas-admin/aas/42/sync",
        data={"description": "Registered physical lab"},
        files={"file": ("physical-lab.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    resolve_fmu_path.assert_not_called()
    read_model_description.assert_not_called()
    sync_fmu_to_basyx.assert_awaited_once_with(
        lab_id="42",
        access_key="42",
        metadata={},
        aasx_bytes=b"aasx-bytes",
        extra_info={"description": "Registered physical lab"},
        fmu_path=None,
        unit_definitions=[],
        required_aas_id="urn:decentralabs:lab:42",
    )
