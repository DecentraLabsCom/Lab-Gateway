from pathlib import Path

import pytest


GATEWAY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = GATEWAY_ROOT.parent
CONTRACT = GATEWAY_ROOT / "docs" / "documentation-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_documentation_contract_is_reachable_from_canonical_indexes():
    assert CONTRACT.exists()
    assert "documentation-contract.md" in _read(GATEWAY_ROOT / "docs" / "README.md")
    assert "documentation-contract.md" in _read(GATEWAY_ROOT / "README.md")
    assert "documentation-contract.md" in _read(
        GATEWAY_ROOT / "blockchain-services" / "SUMMARY.md"
    )
    marketplace_guide = (
        WORKSPACE_ROOT
        / "Marketplace"
        / "docs"
        / "become-a-provider"
        / "authentication-and-authorization.md"
    )
    if marketplace_guide.exists():
        assert "documentation-contract.md" in _read(marketplace_guide)


def test_contract_records_two_phase_access_code_invariant():
    contract = _read(CONTRACT)
    assert "REDEMPTION_PREPARED" in contract
    assert "/commit" in contract
    assert "/release" in contract
    assert "30 seconds" in contract


def test_canonical_guides_do_not_describe_irreversible_one_phase_redemption():
    canonical_guides = [
        GATEWAY_ROOT / "README.md",
        GATEWAY_ROOT / "docs" / "workflows" / "laboratory-connectivity.md",
        GATEWAY_ROOT / "docs" / "configuring-lab-connections" / "guacamole-connections.md",
        GATEWAY_ROOT / "docs" / "edugain" / "edugain-federation.md",
        GATEWAY_ROOT / "docs" / "edugain" / "edugain-federacion.md",
        GATEWAY_ROOT / "docs" / "tutorials" / "tutorial-primera-sesion-laboratorio.md",
        GATEWAY_ROOT / "docs" / "reference" / "operations-and-health.md",
        GATEWAY_ROOT
        / "blockchain-services"
        / "docs"
        / "architecture"
        / "ARCHITECTURE.md",
        WORKSPACE_ROOT
        / "Marketplace"
        / "docs"
        / "become-a-provider"
        / "authentication-and-authorization.md",
        WORKSPACE_ROOT / "copilot-instructions.md",
    ]
    forbidden = (
        "redeems that code once",
        "opaque one-time code exchanged",
        "código opaco de un solo uso; OpenResty lo canjea",
        "Server-side redemption when remote",
    )
    for guide in (guide for guide in canonical_guides if guide.exists()):
        text = _read(guide)
        for phrase in forbidden:
            assert phrase not in text, f"stale phrase {phrase!r} in {guide}"


def test_parallel_backend_variant_is_explicitly_scoped():
    standalone_root = WORKSPACE_ROOT / "Blockchain-Services"
    if not standalone_root.exists():
        pytest.skip("parallel standalone repository is not checked out")
    standalone_readme = _read(standalone_root / "README.md")
    assert "parallel standalone backend variant" in standalone_readme
    assert "canonical" in standalone_readme
    assert "embedded" in standalone_readme
    assert "parallel standalone backend variant" in _read(
        standalone_root / "docs" / "architecture" / "ARCHITECTURE.md"
    )
    assert "parallel standalone variant" in _read(
        standalone_root / "docs" / "services" / "authentication" / "AUTH.md"
    )


def test_external_reservation_timing_is_coordinated_when_sibling_repos_are_present():
    contracts = WORKSPACE_ROOT / "Smart-Contracts"
    marketplace = WORKSPACE_ROOT / "Marketplace"
    backend_properties = (
        GATEWAY_ROOT
        / "blockchain-services"
        / "src"
        / "main"
        / "resources"
        / "application.properties"
    )
    required = [
        contracts / "contracts" / "libraries" / "LibReservationConfig.sol",
        marketplace / "src" / "utils" / "booking" / "reservationLeadTime.js",
        backend_properties,
    ]
    if not all(path.exists() for path in required):
        pytest.skip("cross-project timing sources are not all checked out")

    contract = _read(required[0])
    lead_time = _read(required[1])
    properties = _read(backend_properties)
    assert "PENDING_REQUEST_TTL = 5 minutes" in contract
    assert "RESERVATION_CONFIRMATION_LEAD_TIME = 10 minutes" in contract
    assert "MIN_RESERVATION_LEAD_TIME_SECONDS = 10 * 60" in lead_time
    assert "CONTRACT_EVENT_POLLING_INTERVAL:15" in properties
    assert "CONTRACT_EVENT_PROCESSING_RETRY_DELAY_SECONDS:15" in properties
    assert "CONTRACT_EVENT_CONFIRMATIONS_REQUIRED:12" in properties
