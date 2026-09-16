import hashlib
import json
from pathlib import Path

from aasx_catalog import AasxPackageCatalog


def test_catalog_records_metadata_without_persisting_the_original_file(tmp_path: Path):
    catalog = AasxPackageCatalog(tmp_path)

    package = catalog.record(
        lab_id="42",
        filename="physical-lab.aasx",
        content=b"aasx-bytes",
        sync_result={
            "uploadedAasIds": ["urn:decentralabs:lab:42"],
            "uploadedSubmodelIds": ["urn:example:submodel"],
        },
    )

    assert package["labId"] == "42"
    assert package["filename"] == "physical-lab.aasx"
    assert package["size"] == len(b"aasx-bytes")
    assert package["sha256"] == hashlib.sha256(b"aasx-bytes").hexdigest()
    assert package["storage"] == "basyx"
    assert package["archiveStored"] is False
    assert package["shellIds"] == ["urn:decentralabs:lab:42"]
    assert package["submodelIds"] == ["urn:example:submodel"]
    assert not (tmp_path / "42.aasx").exists()
    assert catalog.list_packages() == [package]
    assert catalog.get("42") == package


def test_catalog_replaces_one_association_per_lab_and_deletes_metadata(tmp_path: Path):
    catalog = AasxPackageCatalog(tmp_path)
    catalog.record(lab_id="7", filename="old.aasx", content=b"old", sync_result={})
    replacement = catalog.record(lab_id="7", filename="new.aasx", content=b"new", sync_result={})

    assert catalog.list_packages() == [replacement]
    assert not (tmp_path / "7.aasx").exists()
    assert catalog.delete("7") is True
    assert catalog.list_packages() == []
    assert catalog.get("7") is None
    assert catalog.delete("7") is False


def test_catalog_delete_cleans_a_legacy_archive_after_basyx_deletion(tmp_path: Path):
    catalog = AasxPackageCatalog(tmp_path)
    catalog.record(lab_id="8", filename="legacy.aasx", content=b"new", sync_result={})
    legacy_archive = tmp_path / "8.aasx"
    legacy_archive.write_bytes(b"legacy-copy")

    assert catalog.delete("8") is True
    assert not legacy_archive.exists()


def test_catalog_reads_legacy_metadata_without_requiring_the_archive(tmp_path: Path):
    (tmp_path / "11.aasx.json").write_text(json.dumps({
        "labId": "11",
        "filename": "unsafe\"\r\nname.aasx",
        "size": "12",
        "shellIds": ["urn:shell:11"],
        "submodelIds": [],
    }), encoding="utf-8")

    package = AasxPackageCatalog(tmp_path).get("11")

    assert package is not None
    assert package["filename"] == "unsafe_name.aasx"
    assert package["size"] == 12
    assert package["storage"] == "basyx"


def test_catalog_rejects_unsafe_lab_ids(tmp_path: Path):
    catalog = AasxPackageCatalog(tmp_path)

    try:
        catalog.record(lab_id="../outside", filename="x.aasx", content=b"x", sync_result={})
    except ValueError as error:
        assert str(error) == "invalid AASX laboratory ID"
    else:
        raise AssertionError("unsafe lab id should be rejected")
