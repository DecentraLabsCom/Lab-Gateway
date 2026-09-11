from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aas_hints_router import create_aas_hints_router


def _client(*, model_description, read_error=None):
    resolve_fmu_path = MagicMock(return_value="/trusted/demo.fmu")
    read_model_description = MagicMock()
    if read_error is not None:
        read_model_description.side_effect = read_error
    else:
        read_model_description.return_value = model_description
    normalize_xml_value = MagicMock(side_effect=lambda value: str(value or "").strip())
    logger = MagicMock()
    app = FastAPI()
    app.include_router(create_aas_hints_router(
        resolve_fmu_path=resolve_fmu_path,
        read_model_description=read_model_description,
        normalize_xml_value=normalize_xml_value,
        logger=logger,
    ))
    return TestClient(app), resolve_fmu_path, read_model_description, logger


def test_hints_route_returns_only_non_empty_metadata_fields():
    client, resolve_fmu_path, read_model_description, _ = _client(
        model_description=SimpleNamespace(
            description="Demo FMU",
            license="",
            author="A. Author",
            version="1.0",
            generationTool=None,
        ),
    )

    response = client.get("/aas-admin/fmu/demo.fmu/hints")

    assert response.status_code == 200
    assert response.json() == {
        "description": "Demo FMU",
        "author": "A. Author",
        "version": "1.0",
    }
    resolve_fmu_path.assert_called_once_with("demo.fmu")
    read_model_description.assert_called_once_with("/trusted/demo.fmu")


def test_hints_route_maps_model_description_errors_to_422():
    client, _, _, logger = _client(
        model_description=None,
        read_error=ValueError("invalid model description"),
    )

    response = client.get("/aas-admin/fmu/broken.fmu/hints")

    assert response.status_code == 422
    assert response.json() == {"detail": "Cannot read FMU model description"}
    logger.error.assert_called_once()