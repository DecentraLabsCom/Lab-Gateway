"""Release-gate contract checks shared by the deployment and E2E suites.

These checks intentionally inspect the values that operators copy into a
deployment. A mismatch here can make an otherwise correct on-chain lifecycle
expire before the listener gets a chance to observe it.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "blockchain-services"
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
        ROOT.parent / "Smart-Contracts" / "test" / "ReleaseGateReservationWindow.t.sol": (
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
