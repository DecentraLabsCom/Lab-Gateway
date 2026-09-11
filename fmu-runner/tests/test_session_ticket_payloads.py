from session_ticket_payloads import (
    build_issue_session_ticket_payload,
    build_redeem_session_ticket_payload,
)


def test_build_issue_session_ticket_payload_coerces_lab_id_and_adds_reservation():
    assert build_issue_session_ticket_payload(
        lab_id=42,
        reservation_key="RES-1",
    ) == {
        "labId": "42",
        "reservationKey": "RES-1",
    }


def test_build_issue_session_ticket_payload_omits_empty_reservation():
    assert build_issue_session_ticket_payload(lab_id="42", reservation_key=None) == {
        "labId": "42",
    }


def test_build_redeem_session_ticket_payload_includes_only_redeem_fields():
    assert build_redeem_session_ticket_payload(
        session_ticket="st_ticket_1",
        lab_id=42,
        reservation_key="RES-1",
    ) == {
        "sessionTicket": "st_ticket_1",
        "labId": "42",
        "reservationKey": "RES-1",
    }
    assert build_redeem_session_ticket_payload(
        session_ticket="st_ticket_1",
        lab_id=None,
        reservation_key=None,
    ) == {"sessionTicket": "st_ticket_1"}