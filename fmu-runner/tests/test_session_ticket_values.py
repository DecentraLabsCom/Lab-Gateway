from session_ticket_values import normalize_ticket_id


def test_normalize_ticket_id_strips_prefix_and_limits_log_identifier():
    assert normalize_ticket_id(" st_1234567890abcdef ") == "1234567890"


def test_normalize_ticket_id_returns_none_for_missing_ticket():
    assert normalize_ticket_id(None) is None
    assert normalize_ticket_id("") is None
    assert normalize_ticket_id("   ") is None