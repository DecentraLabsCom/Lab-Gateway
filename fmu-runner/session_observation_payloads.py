import hashlib


def build_session_observation_payload(
    *,
    session_ticket: str,
    reservation_key: str,
    session_id: str,
    observed_at: int,
) -> dict[str, object]:
    return {
        "reservationKey": reservation_key,
        "fmuTicketId": hashlib.sha256(session_ticket.encode("utf-8")).hexdigest(),
        "sessionId": session_id,
        "accessType": "fmu",
        "observedAt": observed_at,
    }