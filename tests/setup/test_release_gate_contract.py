"""Release-gate contract checks shared by the deployment and E2E suites.

These checks intentionally inspect the values that operators copy into a
deployment. A mismatch here can make an otherwise correct on-chain lifecycle
expire before the listener gets a chance to observe it.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "blockchain-services"
SMART_CONTRACTS = ROOT.parent / "Smart-Contracts"
if not SMART_CONTRACTS.exists():
    SMART_CONTRACTS = ROOT / "Smart-Contracts"
APPLICATION = BACKEND / "src" / "main" / "resources" / "application.properties"
ENV_EXAMPLE = BACKEND / ".env.example"


def _property(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}=(?:\$\{{[^:}}]+:)?([^}}\r\n]+)\}}?$", text)
    assert match, f"Missing property {key}"
    return match.group(1).strip()


def _env(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}=([^\r\n#]+)", text)
    assert match, f"Missing environment variable {key}"
    return match.group(1).strip()


def test_listener_defaults_match_the_five_minute_contract_window():
    text = APPLICATION.read_text(encoding="utf-8")

    assert _property(text, "contract.event.polling.interval.seconds") == "15"
    assert _property(text, "contract.event.processing.retry-delay.seconds") == "15"
    assert _property(text, "contract.event.processing.lease-timeout.seconds") == "120"
    assert _property(text, "contract.event.confirmations.required") == "12"


def test_operator_example_matches_application_defaults_and_has_no_old_ttl():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert _env(text, "CONTRACT_EVENT_POLLING_INTERVAL") == "15"
    assert _env(text, "CONTRACT_EVENT_PROCESSING_RETRY_DELAY_SECONDS") == "15"
    assert _env(text, "CONTRACT_EVENT_PROCESSING_LEASE_TIMEOUT_SECONDS") == "120"
    assert _env(text, "CONTRACT_EVENT_CONFIRMATIONS_REQUIRED") == "12"
    assert not re.search(r"TTL\s*=\s*15\s*min", text, re.IGNORECASE)


def test_release_gate_source_tests_cover_the_high_risk_boundaries():
    expected_fragments = {
        SMART_CONTRACTS / "test" / "ReleaseGateReservationWindow.t.sol": (
            "test_pending_request_expires_at_exactly_five_minutes",
            "test_reservation_start_is_the_effective_deadline_when_it_is_earlier",
        ),
        BACKEND / "src" / "test" / "java" / "decentralabs" / "blockchain" / "service" / "auth" / "SamlValidationServiceTest.java": (
            "shouldRejectResponsesWithMoreThanOneAssertion",
            "shouldRequireTrustedIdpsInWhitelistMode",
        ),
        BACKEND / "src" / "test" / "java" / "decentralabs" / "blockchain" / "service" / "auth" / "WebauthnOnboardingServiceTest.java": (
            "completeOnboarding_rejectsRegistrationWithoutUserVerificationWhenRequired",
        ),
        BACKEND / "src" / "test" / "java" / "decentralabs" / "blockchain" / "service" / "auth" / "InstitutionalConcurrencyMySqlIntegrationTest.java": (
            "anAccessCodeCanBeRedeemedOnlyOnceAcrossTwoReplicas",
            "onlyOneSessionStartedAttestationCanOwnPublicationForAReservation",
        ),
    }

    for path, fragments in expected_fragments.items():
        source = path.read_text(encoding="utf-8")
        for fragment in fragments:
            assert fragment in source, f"Missing release-gate coverage {fragment} in {path}"


def test_gateway_ops_schema_is_migrated_before_full_or_lite_services():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mysql_entrypoint = (ROOT / "mysql" / "000-ensure-user.sh").read_text(encoding="utf-8")
    ops_migrations = ROOT / "ops-migrations" / "sql"
    application = APPLICATION.read_text(encoding="utf-8")

    for migration in (
        "002-labstation-ops.sql",
        "003-energy-policies.sql",
        "004-wake-ops.sql",
    ):
        assert f"./mysql/{migration}" not in compose
        assert migration not in mysql_entrypoint

    assert "ops-schema-migrator:" in compose
    assert "image: flyway/flyway:13.8.0" in compose
    assert "./ops-migrations/sql:/flyway/sql:ro" in compose
    assert "flyway_ops_schema_history" in compose
    assert compose.count("ops-schema-migrator") >= 3
    assert compose.count("service_completed_successfully") >= 2
    assert "spring.flyway.ignore-migration-patterns=versioned:missing" in application

    for legacy_backend_migration in (
        "V10__labstation_ops.sql",
        "V19__gateway_session_observation_outbox.sql",
        "V20__guacamole_token_revocation_queue.sql",
        "V32__guacamole_token_validation_marker.sql",
        "V55__wake_ops_schedules.sql",
        "V56__power_operations.sql",
    ):
        assert not (
            BACKEND / "src" / "main" / "resources" / "db" / "migration"
            / legacy_backend_migration
        ).exists()

    expected_tables = {
        "lab_hosts": "V1__labstation_ops.sql",
        "gateway_session_observation_outbox": "V2__gateway_session_observation_outbox.sql",
        "guacamole_token_revocation_queue": "V3__guacamole_token_revocation_queue.sql",
        "wake_ops_schedules": "V4__wake_ops_schedules.sql",
        "power_operations": "V5__power_operations.sql",
    }
    for table, migration_name in expected_tables.items():
        migration = (ops_migrations / migration_name).read_text(encoding="utf-8")
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration

    validation_marker = (
        ops_migrations / "V6__guacamole_token_validation_marker.sql"
    ).read_text(encoding="utf-8")
    assert "token_validated_at" in validation_marker


def test_setup_contract_job_has_shared_checkout_and_worker_import_dependencies():
    workflow = (ROOT / ".github" / "workflows" / "gateway-tests.yml").read_text(
        encoding="utf-8"
    )

    setup_job = workflow.split("\n  setup-contract-tests:", 1)[1].split(
        "\n  topology-contracts:", 1
    )[0]
    assert "repository: DecentraLabsCom/Smart-Contracts" in setup_job
    assert "path: Smart-Contracts" in setup_job
    assert "-r ops-worker/requirements.txt" in setup_job
