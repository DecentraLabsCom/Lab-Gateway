"""
Tests for ops-worker AAS generator (aas_generator.py).

Tests the pure generation logic (no BaSyx, no DB needed) and the
sync function behaviour when BaSyx is not configured or unreachable.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Make the ops-worker package root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aas_generator as _mod

# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_HOST = {
    "name": "lab-ws-01",
    "address": "192.168.1.100",
    "mac": "00:11:22:33:44:55",
    "labs": ["42"],
}

SAMPLE_HEARTBEAT = {
    "timestamp": "2026-01-01T12:00:00.000Z",
    "summary": {"ready": True},
    "status": {
        "localModeEnabled": False,
        "localSessionActive": False,
    },
    "operations": {
        "lastForcedLogoff": {"timestamp": "2025-12-31T10:00:00Z", "user": "student1"},
        "lastPowerAction": {"timestamp": "2026-01-01T08:00:00Z", "mode": "powerOn"},
    },
}


def _nameplate_props(submodel):
    specific = next(element for element in submodel["submodelElements"] if element["idShort"] == "AssetSpecificProperties")
    return {element["idShort"]: element for element in specific["value"]}


def _technical_props(submodel):
    area = submodel["submodelElements"][1]["value"][0]["value"]
    return {element["idShort"]: element for element in area}


# ── ID / encode helpers ───────────────────────────────────────────────

class TestIdHelpers:
    def test_aas_id_format(self):
        assert _mod._aas_id_for_lab("42") == "urn:decentralabs:lab:42"

    def test_nameplate_submodel_id(self):
        assert _mod._submodel_id_nameplate("42") == "urn:decentralabs:lab:42:sm:nameplate"

    def test_technical_submodel_id(self):
        assert _mod._submodel_id_technical("42") == "urn:decentralabs:lab:42:sm:technicalData"

    def test_encode_id_roundtrip(self):
        import base64
        raw = "urn:decentralabs:lab:42"
        encoded = _mod._encode_id(raw)
        assert "=" not in encoded
        decoded = base64.urlsafe_b64decode(encoded + "==").decode()
        assert decoded == raw


# ── Nameplate submodel ────────────────────────────────────────────────

class TestBuildNameplateSubmodel:
    def test_structure(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        assert sm["modelType"] == "Submodel"
        assert sm["id"] == "urn:decentralabs:lab:42:sm:nameplate"
        assert sm["idShort"] == "Nameplate"

    def test_contains_standard_product_uri(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = {el["idShort"]: el for el in sm["submodelElements"]}
        assert props["URIOfTheProduct"]["value"] == "urn:decentralabs:lab:42"

    def test_contains_host_name(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = _nameplate_props(sm)
        assert props["HostName"]["value"] == "lab-ws-01"

    def test_lab_type_is_physical(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = _nameplate_props(sm)
        assert props["LabType"]["value"] == "PhysicalLaboratory"

    def test_contains_address(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = _nameplate_props(sm)
        assert props["NetworkAddress"]["value"] == "192.168.1.100"

    def test_contains_mac(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = _nameplate_props(sm)
        assert "MacAddress" in props
        assert props["MacAddress"]["value"] == "00:11:22:33:44:55"

    def test_no_mac_when_missing(self):
        host = {**SAMPLE_HOST}
        del host["mac"]
        sm = _mod.build_nameplate_submodel("42", host)
        props = _nameplate_props(sm)
        assert "MacAddress" not in props

    def test_mapped_lab_ids_are_not_copied_from_host_configuration(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        props = {el["idShort"]: el for el in sm["submodelElements"]}
        assert "MappedLabIds" not in props

    def test_semantic_id_present(self):
        sm = _mod.build_nameplate_submodel("42", SAMPLE_HOST)
        assert sm["semanticId"]["keys"][0]["value"] == (
            "https://admin-shell.io/idta/nameplate/3/0/Nameplate"
        )


# ── TechnicalData submodel ────────────────────────────────────────────

class TestBuildTechnicalDataSubmodel:
    def test_structure(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        assert sm["modelType"] == "Submodel"
        assert sm["id"] == "urn:decentralabs:lab:42:sm:technicalData"
        assert sm["idShort"] == "TechnicalData"

    def test_ready_maps_to_status(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        props = _technical_props(sm)
        assert props["LabStatus"]["value"] == "Ready"
        assert props["ReadyFlag"]["value"] == "true"

    def test_common_operational_fields_are_present(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        props = _technical_props(sm)
        assert props["ResourceType"]["value"] == "PhysicalLaboratory"
        assert props["ResourceStatus"]["value"] == "Ready"
        assert props["LastSyncTimestamp"]["value"]

    def test_not_ready_maps_to_status(self):
        hb = {**SAMPLE_HEARTBEAT, "summary": {"ready": False}}
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, hb)
        props = _technical_props(sm)
        assert props["LabStatus"]["value"] == "NotReady"
        assert props["ReadyFlag"]["value"] == "false"

    def test_unknown_ready_is_empty(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, None)
        props = _technical_props(sm)
        assert props["LabStatus"]["value"] == ""
        assert props["ReadyFlag"]["value"] == ""

    def test_local_mode_flag(self):
        hb = {**SAMPLE_HEARTBEAT, "status": {"localModeEnabled": True, "localSessionActive": False}}
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, hb)
        props = _technical_props(sm)
        assert props["LocalModeEnabled"]["value"] == "true"

    def test_heartbeat_timestamp_present(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        props = _technical_props(sm)
        assert props["LastHeartbeatTimestamp"]["value"] == "2026-01-01T12:00:00.000Z"

    def test_power_action_fields(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        props = _technical_props(sm)
        assert props["LastPowerActionMode"]["value"] == "powerOn"
        assert "2026-01-01" in props["LastPowerActionTimestamp"]["value"]

    def test_forced_logoff_fields(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
        props = _technical_props(sm)
        assert props["LastForcedLogoffUser"]["value"] == "student1"

    def test_empty_heartbeat_safe(self):
        # Must not raise even if heartbeat structure is missing fields
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, {})
        assert sm["modelType"] == "Submodel"

    def test_semantic_id_present(self):
        sm = _mod.build_technical_data_submodel("42", SAMPLE_HOST, None)
        assert sm["semanticId"]["keys"][0]["value"] == (
            "0173-1#01-AHX837#002"
        )


class TestBuildExecutionCapabilitiesSubmodel:
    def test_physical_lab_access_capabilities_are_described(self):
        sm = _mod.build_execution_capabilities_submodel("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)

        assert sm["id"] == "urn:decentralabs:lab:42:sm:executionCapabilities"
        assert sm["idShort"] == "CapabilityDescription"
        capabilities = [capability["idShort"] for container in sm["submodelElements"][0]["value"] for capability in container["value"]]
        assert set(capabilities) == {
            "PrepareAccessSession",
            "StartInteractiveSession",
            "EndInteractiveSession",
            "ReadOperationalStatus",
        }
        payload_text = str(sm).lower()
        assert "token" not in payload_text
        assert "password" not in payload_text

    def test_station_capabilities_do_not_claim_heartbeat_when_missing(self):
        sm = _mod.build_execution_capabilities_submodel("42", SAMPLE_HOST, None)
        assert sm["semanticId"]["keys"][0]["value"].endswith("CapabilityDescription/1/0")


# ── AAS Shell ─────────────────────────────────────────────────────────

class TestBuildAasShell:
    def test_shell_id(self):
        shell = _mod.build_physical_aas_shell("42", SAMPLE_HOST)
        assert shell["id"] == "urn:decentralabs:lab:42"

    def test_shell_id_short(self):
        shell = _mod.build_physical_aas_shell("42", SAMPLE_HOST)
        assert shell["idShort"] == "DecentraLabs_Lab_42"

    def test_asset_type_is_not_an_uncontrolled_free_text_value(self):
        shell = _mod.build_physical_aas_shell("42", SAMPLE_HOST)
        assert "assetType" not in shell["assetInformation"]

    def test_references_both_submodels(self):
        shell = _mod.build_physical_aas_shell("42", SAMPLE_HOST)
        refs = [r["keys"][0]["value"] for r in shell["submodels"]]
        assert "urn:decentralabs:lab:42:sm:nameplate" in refs
        assert "urn:decentralabs:lab:42:sm:technicalData" in refs
        assert "urn:decentralabs:lab:42:sm:executionCapabilities" in refs
        assert "urn:decentralabs:lab:42:sm:assetInterfaces" in refs
        assert "urn:decentralabs:lab:42:sm:contactInformation" in refs
        assert "urn:decentralabs:lab:42:sm:handoverDocumentation" in refs

    def test_description_contains_host_name(self):
        shell = _mod.build_physical_aas_shell("42", SAMPLE_HOST)
        desc = " ".join(d["text"] for d in shell["description"])
        assert "lab-ws-01" in desc

    def test_registered_description_overrides_host_fallback(self):
        shell = _mod.build_physical_aas_shell(
            "42",
            SAMPLE_HOST,
            {"description": "Registered remote laboratory"},
        )
        desc = " ".join(d["text"] for d in shell["description"])
        assert desc == "Registered remote laboratory"

    def test_registered_metadata_is_published_in_the_nameplate(self):
        submodel = _mod.build_nameplate_submodel(
            "42",
            SAMPLE_HOST,
            {
                "license": "https://example.test/terms.html",
                "documentationUrls": [
                    "https://example.test/manual.pdf",
                    "https://example.test/guide.html",
                ],
                "contactEmail": "lab@example.test",
            },
        )
        contact = _mod.build_contact_information_submodel("42", {"contactEmail": "lab@example.test"})
        assert contact["submodelElements"][0]["value"][0]["value"][0]["value"] == "lab@example.test"
        handover = _mod.build_handover_documentation_submodel(
            "42",
            {
                "license": "https://example.test/terms.html",
                "documentationUrls": [
                    "https://example.test/manual.pdf",
                    "https://example.test/guide.html",
                ],
            },
        )
        files = [
            document["value"][1]["value"][0]["value"][3]["value"][0]["value"]
            for document in handover["submodelElements"][0]["value"]
        ]
        assert files == [
            "https://example.test/terms.html",
            "https://example.test/manual.pdf",
            "https://example.test/guide.html",
        ]


# ── sync_lab_to_basyx degradation ─────────────────────────────────────

class TestSyncLabToBasyxDegradation:
    def test_disabled_when_no_url(self):
        original = _mod.BASYX_AAS_URL
        _mod.BASYX_AAS_URL = ""
        try:
            result = _mod.sync_lab_to_basyx("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
            assert result.get("disabled") is True
            assert "error" not in result
            assert result.get("synced") is None
        finally:
            _mod.BASYX_AAS_URL = original

    def test_error_when_basyx_unreachable(self):
        original = _mod.BASYX_AAS_URL
        _mod.BASYX_AAS_URL = "https://127.0.0.1:19999"  # nothing listening
        try:
            result = _mod.sync_lab_to_basyx("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)
            assert "error" in result
            assert "BaSyx unreachable" in result["error"] or "BaSyx timeout" in result["error"]
            assert result.get("synced") is None
        finally:
            _mod.BASYX_AAS_URL = original

    @pytest.mark.parametrize("lab_id", ["../etc/passwd", "lab?id=1", "urn:decentralabs:lab:1"])
    def test_rejects_invalid_lab_id_before_network(self, lab_id):
        original = _mod.BASYX_AAS_URL
        _mod.BASYX_AAS_URL = "https://basyx-mock:8081"
        try:
            with patch("aas_generator.requests.Session") as mock_session:
                result = _mod.sync_lab_to_basyx(lab_id, SAMPLE_HOST, SAMPLE_HEARTBEAT)

            assert result == {"error": "AAS lab ID rejected", "created": False, "updated": False}
            mock_session.assert_not_called()
        finally:
            _mod.BASYX_AAS_URL = original

    def test_put_or_post_rejects_untrusted_resource_path(self):
        session = MagicMock()

        with pytest.raises(ValueError):
            _mod._put_or_post(
                session,
                "https://basyx-mock:8081",
                "/submodels/../etc/passwd",
                "/submodels",
                {},
            )

        session.put.assert_not_called()

    def test_put_or_post_rejects_untrusted_endpoint(self):
        session = MagicMock()

        with pytest.raises(ValueError):
            _mod._put_or_post(
                session,
                "https://evil.example",
                "/submodels/abc",
                "/submodels",
                {},
            )

        session.put.assert_not_called()

    def test_success_path(self):
        """Happy path: all BaSyx calls return 201."""
        original = _mod.BASYX_AAS_URL
        _mod.BASYX_AAS_URL = "https://basyx-mock:8081"
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.text = ""

            with patch("aas_generator.requests.Session") as MockSession:
                session_instance = MagicMock()
                MockSession.return_value = session_instance
                session_instance.put.return_value = mock_resp
                session_instance.headers = {}

                result = _mod.sync_lab_to_basyx("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)

            assert result.get("synced") is True
            assert result.get("created") is True
            assert "error" not in result
            session_instance.close.assert_called_once_with()
        finally:
            _mod.BASYX_AAS_URL = original

    def test_error_propagated_on_bad_response(self):
        """If BaSyx returns 500 for nameplate PUT and 404 POST fallback, sync returns error."""
        original = _mod.BASYX_AAS_URL
        _mod.BASYX_AAS_URL = "https://basyx-mock:8081"
        try:
            mock_put = MagicMock()
            mock_put.status_code = 500
            mock_put.text = "internal server error"

            with patch("aas_generator.requests.Session") as MockSession:
                session_instance = MagicMock()
                MockSession.return_value = session_instance
                session_instance.put.return_value = mock_put
                session_instance.headers = {}

                result = _mod.sync_lab_to_basyx("42", SAMPLE_HOST, SAMPLE_HEARTBEAT)

            assert "error" in result
            assert result.get("synced") is None
            session_instance.close.assert_called_once_with()
        finally:
            _mod.BASYX_AAS_URL = original
