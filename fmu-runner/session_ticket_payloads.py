from typing import Optional


def build_issue_session_ticket_payload(
    *,
    lab_id: object,
    reservation_key: Optional[str],
) -> dict[str, str]:
    payload = {"labId": str(lab_id)}
    if reservation_key:
        payload["reservationKey"] = reservation_key
    return payload


def build_redeem_session_ticket_payload(
    *,
    session_ticket: str,
    lab_id: Optional[object],
    reservation_key: Optional[object],
) -> dict[str, str]:
    payload = {"sessionTicket": session_ticket}
    if lab_id:
        payload["labId"] = str(lab_id)
    if reservation_key:
        payload["reservationKey"] = str(reservation_key)
    return payload