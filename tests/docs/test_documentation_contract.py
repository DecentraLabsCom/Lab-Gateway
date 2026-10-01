from pathlib import Path

import pytest


GATEWAY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = GATEWAY_ROOT.parent
CONTRACT = GATEWAY_ROOT / "docs" / "documentation-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_documentation_contract_is_reachable_from_gateway_indexes():
    assert CONTRACT.exists()
    assert "documentation-contract.md" in _read(GATEWAY_ROOT / "docs" / "README.md")
    assert "documentation-contract.md" in _read(GATEWAY_ROOT / "README.md")
    backend_summary = GATEWAY_ROOT / "blockchain-services" / "SUMMARY.md"
    assert backend_summary.exists()
    assert "parallel standalone backend variant" not in _read(backend_summary)
    marketplace_guide = (
        WORKSPACE_ROOT
        / "Marketplace"
        / "docs"
        / "become-a-provider"
        / "authentication-and-authorization.md"
    )
    if marketplace_guide.exists():
        assert "documentation-contract.md" in _read(marketplace_guide)


def test_quick_start_explains_compose_secret_materialization():
    readme = _read(GATEWAY_ROOT / "README.md")
    assert "validate-gateway-env.py" in readme
    assert "sync-compose-secrets.sh" in readme
    assert "Validate-GatewayEnv.ps1" in readme
    assert "Sync-ComposeSecrets.ps1" in readme


def test_gateway_configuration_uses_the_implemented_forwarded_ip_setting():
    configuration = _read(GATEWAY_ROOT / "docs" / "reference" / "configuration.md")
    assert "ADMIN_TRUST_FORWARDED_IP" in configuration
    assert "TRUST_PROXY_HEADERS" not in configuration


def test_documented_ops_controls_are_exposed_by_compose():
    compose = _read(GATEWAY_ROOT / "docker-compose.yml")
    for variable in (
        "OPS_ALLOWED_COMMANDS",
        "OPS_RESERVATION_LOOKBACK",
        "OPS_RESERVATION_RETRY_COOLDOWN",
        "OPS_RESERVATION_MAX_BATCH",
        "NOTIFICATION_SERVICE_URL",
        "NOTIFICATION_SERVICE_RECIPIENTS",
        "NOTIFICATION_SERVICE_RETRY_ATTEMPTS",
        "NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS",
        "OPS_DISCOVERY_TIMEOUT_SECONDS",
        "OPS_DISCOVERY_LABSTATION_PORTS",
        "OPS_DISCOVERY_LABSTATION_PATHS",
    ):
        assert f"{variable}=" in compose


def test_primary_summary_points_to_backend_documentation():
    summary = _read(GATEWAY_ROOT / "SUMMARY.md")
    assert "blockchain-services/SUMMARY.md" in summary


def test_root_environment_template_describes_current_gateway_modes():
    env_example = _read(GATEWAY_ROOT / ".env.example")
    header = "\n".join(env_example.splitlines()[:4]).lower()
    assert "full/lite" in header
    assert "auth2" not in header


def test_oidc_integration_scope_distinguishes_mock_coverage_from_production_support():
    integration = _read(GATEWAY_ROOT / "tests" / "integration" / "README.md")
    assert "OIDC discovery" in integration
    assert "provider mode" in integration
    assert "mock backend" in integration


def test_contract_records_two_phase_access_code_invariant():
    contract = _read(CONTRACT)
    assert "REDEMPTION_PREPARED" in contract
    assert "/commit" in contract
    assert "/release" in contract
    assert "30 seconds" in contract


def test_protocol_guides_do_not_describe_irreversible_one_phase_redemption():
    protocol_guides = [
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
    for guide in (guide for guide in protocol_guides if guide.exists()):
        text = _read(guide)
        for phrase in forbidden:
            assert phrase not in text, f"stale phrase {phrase!r} in {guide}"


def test_backend_checkouts_share_one_documentation_identity():
    backend_paths = [
        GATEWAY_ROOT / "blockchain-services",
        WORKSPACE_ROOT / "Blockchain-Services",
    ]
    stale_terms = (
        "canonical backend",
        "parallel standalone backend variant",
        "parallel standalone variant",
        "embedded canonical",
    )
    for backend_root in (path for path in backend_paths if path.exists()):
        for relative in (
            "README.md",
            "SUMMARY.md",
            "docs/architecture/ARCHITECTURE.md",
            "docs/configuration/DEPLOYMENT.md",
            "docs/services/authentication/AUTH.md",
        ):
            document = backend_root / relative
            assert document.exists(), document
            content = _read(document).lower()
            for term in stale_terms:
                assert term not in content, f"stale term {term!r} in {document}"


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
