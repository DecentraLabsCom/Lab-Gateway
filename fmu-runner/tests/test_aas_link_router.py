import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aas_link_router import create_aas_link_router


def _client(tmp_path: Path):
    def get_link_path(access_key: str) -> Path:
        return tmp_path / f"{access_key}.aas-link.json"

    app = FastAPI()
    app.include_router(create_aas_link_router(get_link_path=get_link_path))
    return TestClient(app)


def test_create_and_resolve_link_use_injected_storage_path(tmp_path):
    client = _client(tmp_path)

    create_response = client.post(
        "/aas-admin/fmu/motor.fmu/aas-link",
        json={"aasId": "urn:external:aas:motor", "labId": "42"},
    )
    resolve_response = client.get(
        "/aas-admin/resolve-aas-id",
        params={"shellId": "urn:decentralabs:lab:42"},
    )

    assert create_response.status_code == 200
    assert resolve_response.json() == {
        "targetId": "urn:external:aas:motor",
        "override": True,
    }
    assert json.loads((tmp_path / "motor.fmu.aas-link.json").read_text()) == {
        "aasId": "urn:external:aas:motor",
        "labId": "42",
    }
    assert json.loads((tmp_path / "42.aas-link.json").read_text()) == {
        "aasId": "urn:external:aas:motor",
        "labId": "42",
    }


def test_get_link_returns_not_found_without_a_configured_file(tmp_path):
    response = _client(tmp_path).get("/aas-admin/fmu/missing.fmu/aas-link")

    assert response.status_code == 404