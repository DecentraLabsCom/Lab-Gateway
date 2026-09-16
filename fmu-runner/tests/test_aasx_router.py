from pathlib import Path
from unittest.mock import AsyncMock

from aasx_catalog import AasxPackageCatalog
from aasx_router import create_aasx_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(tmp_path: Path, delete_resources=None):
    catalog = AasxPackageCatalog(tmp_path)
    delete_calls = []
    serialize_calls = []

    async def default_delete_resources(**kwargs):
        delete_calls.append(kwargs)
        return {
            "deletedAasIds": kwargs["shell_ids"],
            "deletedSubmodelIds": kwargs["submodel_ids"],
        }

    async def default_serialize_resources(**kwargs):
        serialize_calls.append(kwargs)
        return {
            "content": b"generated-aasx",
            "mediaType": "application/asset-administration-shell-package+xml",
        }

    app = FastAPI()
    app.include_router(create_aasx_router(
        catalog=catalog,
        serialize_resources=default_serialize_resources,
        delete_resources=delete_resources or default_delete_resources,
    ))
    return TestClient(app), catalog, delete_calls, serialize_calls


def test_catalog_view_download_and_delete_follow_the_lab_association(tmp_path: Path):
    client, catalog, delete_calls, serialize_calls = _client(tmp_path)
    catalog.record(
        lab_id="42",
        filename="physical-lab.aasx",
        content=b"aasx-bytes",
        sync_result={"uploadedAasIds": ["urn:decentralabs:lab:42"]},
    )

    catalog_response = client.get("/aas-admin/aas/catalog")
    view = client.get("/aas-admin/aas/42/view")
    download = client.get("/aas-admin/aas/42/download")
    deleted = client.delete("/aas-admin/aas/42")

    assert catalog_response.status_code == 200
    assert catalog_response.json()["packages"][0]["labId"] == "42"
    assert view.status_code == 200
    assert view.json()["filename"] == "physical-lab.aasx"
    assert view.json()["shellIds"] == ["urn:decentralabs:lab:42"]
    assert download.status_code == 200
    assert download.content == b"generated-aasx"
    assert download.headers["content-disposition"] == 'attachment; filename="physical-lab.aasx"'
    assert serialize_calls == [{
        "shell_ids": ["urn:decentralabs:lab:42"],
        "submodel_ids": [],
    }]
    assert deleted.status_code == 200
    assert delete_calls == [{
        "shell_ids": ["urn:decentralabs:lab:42"],
        "submodel_ids": [],
    }]
    assert deleted.json() == {
        "deleted": True,
        "labId": "42",
        "deletedAasIds": ["urn:decentralabs:lab:42"],
        "deletedSubmodelIds": [],
    }


def test_aasx_router_returns_not_found_for_unknown_packages(tmp_path: Path):
    client, _, _, _ = _client(tmp_path)

    assert client.get("/aas-admin/aas/missing/view").status_code == 404
    assert client.get("/aas-admin/aas/missing/download").status_code == 404
    assert client.delete("/aas-admin/aas/missing").status_code == 404


def test_aasx_router_keeps_the_catalog_when_basyx_deletion_fails(tmp_path: Path):
    async def delete_resources(**kwargs):
        return {"error": "BaSyx resource deletion failed", "failed": [{"status": 500}]}

    client, catalog, _, _ = _client(tmp_path, delete_resources=delete_resources)
    catalog.record(
        lab_id="42",
        filename="physical-lab.aasx",
        content=b"aasx-bytes",
        sync_result={"uploadedAasIds": ["urn:decentralabs:lab:42"]},
    )

    deleted = client.delete("/aas-admin/aas/42")

    assert deleted.status_code == 502
    assert catalog.get("42") is not None


def test_aasx_router_returns_gateway_error_when_serialization_fails(tmp_path: Path):
    async def serialize_resources(**kwargs):
        return {"error": "BaSyx serialization failed"}

    catalog = AasxPackageCatalog(tmp_path)
    catalog.record(
        lab_id="42",
        filename="physical-lab.aasx",
        content=b"aasx-bytes",
        sync_result={"uploadedAasIds": ["urn:decentralabs:lab:42"]},
    )
    app = FastAPI()
    app.include_router(create_aasx_router(
        catalog=catalog,
        serialize_resources=serialize_resources,
        delete_resources=AsyncMock(),
    ))

    response = TestClient(app).get("/aas-admin/aas/42/download")

    assert response.status_code == 502
