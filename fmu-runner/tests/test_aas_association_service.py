from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from aas_association_service import AasAssociationService
from aasx_catalog import AasxPackageCatalog


def _service(tmp_path: Path, discovered):
    catalog = AasxPackageCatalog(tmp_path / "catalog")
    delete_resources = AsyncMock(return_value={
        "deletedAasIds": ["urn:decentralabs:lab:3"],
        "deletedSubmodelIds": ["urn:decentralabs:lab:3:sm:technicalData"],
    })

    async def discover():
        return discovered

    return (
        AasAssociationService(
            package_catalog=catalog,
            link_data_path=tmp_path / "links",
            discover_basyx_shells=discover,
            delete_resources=delete_resources,
        ),
        catalog,
        delete_resources,
    )


@pytest.mark.asyncio
async def test_lists_imported_generated_and_linked_associations_with_precedence(tmp_path: Path):
    service, catalog, _ = _service(tmp_path, {
        "shells": [
            {
                "id": "urn:decentralabs:lab:1",
                "submodelIds": ["urn:decentralabs:lab:1:sm:technicalData"],
            },
            {
                "id": "urn:decentralabs:lab:3",
                "submodelIds": ["urn:decentralabs:lab:3:sm:technicalData"],
                "updatedAt": "2026-09-25T12:34:56+00:00",
            },
        ],
    })
    catalog.record(
        lab_id="1",
        filename="prepared.aasx",
        content=b"aasx",
        sync_result={"uploadedAasIds": ["urn:decentralabs:lab:1"]},
    )
    links_path = tmp_path / "links"
    links_path.mkdir()
    (links_path / "2.aas-link.json").write_text(
        '{"labId":"2","aasId":"urn:external:aas:2","submodelIds":["urn:external:sm:2"]}',
        encoding="utf-8",
    )

    result = await service.list_associations()

    assert [(item["labId"], item["source"]) for item in result["associations"]] == [
        ("1", "imported"),
        ("2", "linked"),
        ("3", "generated"),
    ]
    assert result["associations"][0]["filename"] == "prepared.aasx"
    assert result["associations"][1]["targetAasId"] == "urn:external:aas:2"
    assert result["associations"][2]["shellIds"] == ["urn:decentralabs:lab:3"]
    assert result["associations"][2]["updatedAt"] == "2026-09-25T12:34:56+00:00"


@pytest.mark.asyncio
async def test_keeps_local_associations_visible_when_basyx_discovery_fails(tmp_path: Path):
    service, catalog, _ = _service(tmp_path, {"error": "BaSyx unavailable"})
    catalog.record(lab_id="1", filename="prepared.aasx", content=b"aasx", sync_result={})

    result = await service.list_associations()

    assert [item["labId"] for item in result["associations"]] == ["1"]
    assert result["warning"] == "BaSyx unavailable"


@pytest.mark.asyncio
async def test_deleting_linked_association_only_removes_the_link(tmp_path: Path):
    service, _, delete_resources = _service(tmp_path, {"shells": []})
    links_path = tmp_path / "links"
    links_path.mkdir()
    link = {"labId": "2", "aasId": "urn:external:aas:2"}
    (links_path / "2.aas-link.json").write_text('{"labId":"2","aasId":"urn:external:aas:2"}', encoding="utf-8")

    result = await service.delete_association("2")

    assert result == {"deleted": True, "unlinked": True, "labId": "2", "source": "linked"}
    assert not (links_path / "2.aas-link.json").exists()
    delete_resources.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleting_generated_association_removes_basyx_resources(tmp_path: Path):
    service, _, delete_resources = _service(tmp_path, {
        "shells": [{
            "id": "urn:decentralabs:lab:3",
            "submodelIds": ["urn:decentralabs:lab:3:sm:technicalData"],
        }],
    })

    result = await service.delete_association("3")

    assert result["deleted"] is True
    assert result["source"] == "generated"
    delete_resources.assert_awaited_once_with(
        shell_ids=["urn:decentralabs:lab:3"],
        submodel_ids=["urn:decentralabs:lab:3:sm:technicalData"],
    )
