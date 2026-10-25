from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aas_sync_router import create_aas_sync_router


def _client(*, metadata=None, sync_result=None, runtime_status=None, record_aasx=None, access_policy_status=None):
    resolve_fmu_path = MagicMock(return_value=Path("/trusted/demo.fmu"))
    read_model_description = MagicMock(return_value=SimpleNamespace(description="Embedded", license="MIT"))
    metadata_builder = MagicMock(return_value=metadata or {"description": "Embedded", "license": "MIT", "unitDefinitions": []})
    sync_fmu_to_basyx = AsyncMock(return_value=sync_result or {"synced": True})
    get_runtime_status = AsyncMock(return_value=runtime_status) if runtime_status is not None else None
    logger = MagicMock()
    app = FastAPI()
    app.include_router(create_aas_sync_router(
        resolve_fmu_path=resolve_fmu_path,
        read_model_description=read_model_description,
        metadata_builder=metadata_builder,
        sync_fmu_to_basyx=sync_fmu_to_basyx,
        logger=logger,
        get_runtime_status=get_runtime_status,
        record_aasx=record_aasx,
        get_access_policy_status=access_policy_status,
    ))
    return TestClient(app), resolve_fmu_path, read_model_description, metadata_builder, sync_fmu_to_basyx, get_runtime_status


def test_sync_route_builds_metadata_and_preserves_query_fields():
    client, resolve_fmu_path, read_model_description, metadata_builder, sync_fmu_to_basyx, _ = _client()

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
        required_aas_id=None,
        force_regenerate_access_policy=False,
        runtime_info=None,
    )


def test_sync_route_accepts_a_managed_threejs_app_asset_url():
    asset_url = f"/digital-twin-apps/42/{'a' * 64}/index.html"
    client, _, _, _, sync_fmu_to_basyx, _ = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        params={"labId": "42", "digitalTwinAssetUrl": asset_url},
    )

    assert response.status_code == 200
    assert sync_fmu_to_basyx.await_args is not None
    assert sync_fmu_to_basyx.await_args.kwargs["extra_info"]["digitalTwinAssetUrl"] == asset_url


def test_sync_route_rejects_non_https_external_scene_urls():
    client, _, _, _, sync_fmu_to_basyx, _ = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        params={"labId": "42", "digitalTwinAssetUrl": "http://assets.example.test/scene.glb"},
    )

    assert response.status_code == 400
    sync_fmu_to_basyx.assert_not_awaited()


def test_sync_route_publishes_runtime_status_for_generated_fmu():
    runtime_status = {
        "status": "UP",
        "backendMode": "local",
        "activeSimulationCount": 1,
        "maxConcurrentSimulations": 4,
    }
    client, _, _, _, sync_fmu_to_basyx, get_runtime_status = _client(
        runtime_status=runtime_status,
    )

    response = client.post("/aas-admin/fmu/demo.fmu/sync?labId=42")

    assert response.status_code == 200
    assert get_runtime_status is not None
    get_runtime_status.assert_awaited_once_with("42")
    assert sync_fmu_to_basyx.await_args is not None
    assert sync_fmu_to_basyx.await_args.kwargs["runtime_info"] == runtime_status


def test_fmu_sync_route_reads_metadata_before_accepting_multipart_aasx():
    client, resolve_fmu_path, read_model_description, metadata_builder, sync_fmu_to_basyx, _ = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        data={"labId": "99"},
        files={"file": ("demo.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    resolve_fmu_path.assert_called_once_with("demo.fmu")
    read_model_description.assert_called_once_with(str(Path("/trusted/demo.fmu")))
    metadata_builder.assert_called_once()
    sync_call = sync_fmu_to_basyx.await_args
    assert sync_call is not None
    assert sync_call.kwargs["lab_id"] == "99"
    assert sync_call.kwargs["aasx_bytes"] == b"aasx-bytes"
    assert sync_call.kwargs["required_aas_id"] == "urn:decentralabs:lab:99"


def test_fmu_sync_route_rejects_oversized_aasx_upload_before_sync(monkeypatch):
    import aas_sync_router

    monkeypatch.setattr(aas_sync_router, "MAX_AASX_UPLOAD_BYTES", 8)
    client, _, _, _, sync_fmu_to_basyx, _ = _client()

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        data={"labId": "99"},
        files={"file": ("demo.aasx", b"123456789", "application/octet-stream")},
    )

    assert response.status_code == 413
    sync_fmu_to_basyx.assert_not_awaited()


def test_sync_route_passes_explicit_access_policy_regeneration():
    client, _, _, _, sync_fmu_to_basyx, _ = _client()
    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync?labId=42&regenerateAccessPolicy=true",
    )
    assert response.status_code == 200
    sync_call = sync_fmu_to_basyx.await_args
    assert sync_call is not None
    assert sync_call.kwargs["force_regenerate_access_policy"] is True


def test_sync_route_rejects_policy_regeneration_with_aasx_upload():
    client, _, _, _, sync_fmu_to_basyx, _ = _client()
    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync?regenerateAccessPolicy=true",
        data={"labId": "42"},
        files={"file": ("demo.aasx", b"aasx-bytes", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Remove the AASX upload before regenerating default access rules"
    sync_fmu_to_basyx.assert_not_awaited()


def test_access_policy_status_is_admin_safe_and_not_cached():
    from fastapi import FastAPI

    status = {"state": "generated", "policySource": "aas-generated", "regenerationAvailable": True}
    get_policy_status = AsyncMock(return_value=status)
    client, *_ = _client(access_policy_status=get_policy_status)
    response = client.get("/aas-admin/fmu/motor.fmu/access-policy?labId=42")
    assert response.status_code == 200
    assert response.json() == status
    assert response.headers["cache-control"] == "no-store"
    get_policy_status.assert_awaited_once_with("42", "motor.fmu")


def test_access_policy_status_fails_closed_when_callback_is_unavailable():
    client, *_ = _client()
    response = client.get("/aas-admin/fmu/motor.fmu/access-policy?labId=42")
    assert response.status_code == 503


def test_fmu_route_records_aasx_association_when_the_lab_id_is_explicit():
    from unittest.mock import MagicMock

    record_aasx = MagicMock(return_value={"labId": "99", "filename": "demo.aasx"})
    client, _, _, _, _, _ = _client(record_aasx=record_aasx)

    response = client.post(
        "/aas-admin/fmu/demo.fmu/sync",
        data={"labId": "99"},
        files={"file": ("demo.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    record_aasx.assert_called_once()
    assert record_aasx.call_args.kwargs["lab_id"] == "99"
    assert record_aasx.call_args.kwargs["filename"] == "demo.aasx"
    assert record_aasx.call_args.kwargs["content"] == b"aasx-bytes"


def test_generic_resource_route_accepts_physical_lab_aasx_without_reading_fmu_metadata():
    client, resolve_fmu_path, read_model_description, _, sync_fmu_to_basyx, _ = _client()

    response = client.post(
        "/aas-admin/aas/42/sync",
        data={"description": "Registered physical lab"},
        files={"file": ("physical-lab.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    resolve_fmu_path.assert_not_called()
    read_model_description.assert_not_called()
    assert sync_fmu_to_basyx.await_args is not None
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


def test_generic_resource_route_records_aasx_after_successful_import():
    from unittest.mock import MagicMock

    record_aasx = MagicMock(return_value={"labId": "42", "filename": "physical-lab.aasx"})
    client, _, _, _, _, _ = _client(record_aasx=record_aasx)

    response = client.post(
        "/aas-admin/aas/42/sync",
        files={"file": ("physical-lab.aasx", b"aasx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    record_aasx.assert_called_once()
    assert record_aasx.call_args.kwargs["lab_id"] == "42"
    assert record_aasx.call_args.kwargs["filename"] == "physical-lab.aasx"
    assert record_aasx.call_args.kwargs["content"] == b"aasx-bytes"
