import hashlib
import json
import struct
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import digital_twin_assets_router as assets_router
from digital_twin_assets_router import create_digital_twin_assets_router


_ADMIN_TOKEN = "test-admin-token"
_FMU_ACCESS_KEY = "smart-factory/SmartFactoryCell.fmu"


def _glb(document: dict | None = None) -> bytes:
    json_chunk = json.dumps(
        document or {"asset": {"version": "2.0"}}, separators=(",", ":")
    ).encode()
    json_chunk += b" " * (-len(json_chunk) % 4)
    total_length = 12 + 8 + len(json_chunk)
    return struct.pack("<4sII", b"glTF", 2, total_length) + struct.pack(
        "<II", len(json_chunk), 0x4E4F534A
    ) + json_chunk


def _client(
    tmp_path: Path,
    *,
    fmu_backend_mode: str = "station",
    fmu_data_root: Path | None = None,
    resolve_local_fmu_path=None,
    station_base_url: str = "",
    station_internal_token: str = "",
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_digital_twin_assets_router(
            asset_root=tmp_path / "scenes",
            lab_manager_token=_ADMIN_TOKEN,
            fmu_backend_mode=fmu_backend_mode,
            fmu_data_root=fmu_data_root or tmp_path / "fmu-data",
            resolve_local_fmu_path=resolve_local_fmu_path,
            station_base_url=station_base_url,
            station_internal_token=station_internal_token,
        )
    )
    return TestClient(app)


def test_upload_requires_admin_authentication(tmp_path):
    response = _client(tmp_path).put(
        "/admin/digital-twin-scenes/42",
        content=_glb(),
        headers={"Content-Type": "model/gltf-binary"},
    )

    assert response.status_code == 401
    assert not (tmp_path / "scenes" / "42").exists()


def test_upload_valid_glb_is_stored_by_content_hash(tmp_path):
    content = _glb()
    response = _client(tmp_path).put(
        "/admin/digital-twin-scenes/42",
        content=content,
        headers={
            "Content-Type": "model/gltf-binary",
            "X-Digital-Twin-Admin-Token": _ADMIN_TOKEN,
        },
    )
    digest = hashlib.sha256(content).hexdigest()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "path": f"/digital-twin-scenes/42/{digest}.glb",
        "sha256": digest,
        "size": len(content),
    }
    assert (tmp_path / "scenes" / "42" / f"{digest}.glb").read_bytes() == content


def test_import_from_local_gateway_uses_companion_glb_and_auth(tmp_path):
    data_root = tmp_path / "fmu-data"
    fmu_path = data_root / "smart-factory" / "SmartFactoryCell.fmu"
    scene_path = fmu_path.with_suffix(".glb")
    fmu_path.parent.mkdir(parents=True)
    fmu_path.write_bytes(b"FMU placeholder")
    content = _glb()
    scene_path.write_bytes(content)
    resolved_access_keys = []

    def resolve_local_fmu_path(access_key: str) -> Path:
        resolved_access_keys.append(access_key)
        return data_root / access_key

    response = _client(
        tmp_path,
        fmu_backend_mode="local",
        fmu_data_root=data_root,
        resolve_local_fmu_path=resolve_local_fmu_path,
    ).post(
        "/admin/digital-twin-scenes/42/from-fmu",
        json={"accessKey": _FMU_ACCESS_KEY},
        headers={"X-Digital-Twin-Admin-Token": _ADMIN_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "gateway"
    assert response.json()["accessKey"] == _FMU_ACCESS_KEY
    assert response.json()["sha256"] == hashlib.sha256(content).hexdigest()
    assert resolved_access_keys == [_FMU_ACCESS_KEY]


def test_import_from_station_fetches_authenticated_companion_glb(tmp_path, monkeypatch):
    content = _glb()
    station_requests = []

    class FakeResponse:
        status_code = 200
        headers = {
            "content-type": "model/gltf-binary",
            "content-length": str(len(content)),
        }

        async def aiter_bytes(self):
            yield content[:8]
            yield content[8:]

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_):
            return False

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            station_requests.append({"clientOptions": kwargs})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def stream(self, method, url, *, headers):
            station_requests.append({"method": method, "url": url, "headers": headers})
            return FakeStream()

    monkeypatch.setattr(assets_router.httpx, "AsyncClient", FakeAsyncClient)
    response = _client(
        tmp_path,
        fmu_backend_mode="station",
        station_base_url="http://lab-station:8080/api/",
        station_internal_token="station-secret",
    ).post(
        "/admin/digital-twin-scenes/42/from-fmu",
        json={"accessKey": _FMU_ACCESS_KEY},
        headers={"X-Digital-Twin-Admin-Token": _ADMIN_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "station"
    assert response.json()["sha256"] == hashlib.sha256(content).hexdigest()
    assert station_requests[1] == {
        "method": "GET",
        "url": "http://lab-station:8080/api/internal/fmu/companion-scene",
        "headers": {
            "X-Internal-Session-Token": "station-secret",
            "X-FMU-Access-Key": _FMU_ACCESS_KEY,
        },
    }


def test_import_rejects_external_glb_resources(tmp_path):
    external_scene = _glb(
        {
            "asset": {"version": "2.0"},
            "buffers": [{"uri": "https://example.test/scene.bin"}],
        }
    )
    data_root = tmp_path / "fmu-data"
    fmu_path = data_root / _FMU_ACCESS_KEY
    fmu_path.parent.mkdir(parents=True)
    fmu_path.write_bytes(b"FMU placeholder")
    fmu_path.with_suffix(".glb").write_bytes(external_scene)

    response = _client(
        tmp_path,
        fmu_backend_mode="local",
        fmu_data_root=data_root,
        resolve_local_fmu_path=lambda access_key: data_root / access_key,
    ).post(
        "/admin/digital-twin-scenes/42/from-fmu",
        json={"accessKey": _FMU_ACCESS_KEY},
        headers={"X-Digital-Twin-Admin-Token": _ADMIN_TOKEN},
    )

    assert response.status_code == 400
    assert "external resources" in response.json()["detail"]
