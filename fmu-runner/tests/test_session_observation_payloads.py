import hashlib

from session_observation_payloads import build_session_observation_payload


def test_build_session_observation_payload_hashes_ticket_and_preserves_identity():
    assert build_session_observation_payload(
        session_ticket="st_secret-ticket",
        reservation_key="RES-1",
        session_id="sess-fmu-1",
        observed_at=1735689600,
    ) == {
        "reservationKey": "RES-1",
        "fmuTicketId": hashlib.sha256(b"st_secret-ticket").hexdigest(),
        "sessionId": "sess-fmu-1",
        "accessType": "fmu",
        "observedAt": 1735689600,
    }