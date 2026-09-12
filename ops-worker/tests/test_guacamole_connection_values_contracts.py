import re

import pytest

import worker


def test_parse_guacamole_selector_contract_strips_whitespace_and_returns_integer():
    assert worker.parse_guacamole_selector("  guac:id:42  ") == 42


@pytest.mark.parametrize(
    "selector",
    ["", "guac:id:0", "guac:id:01", "guac:id:-1", "guac:42", "42", None],
)
def test_parse_guacamole_selector_contract_rejects_invalid_formats(selector):
    with pytest.raises(ValueError, match="selector must use guac:id:<connection_id>"):
        worker.parse_guacamole_selector(selector)


def test_parse_guacamole_selector_contract_uses_current_pattern(monkeypatch):
    monkeypatch.setattr(worker, "GUAC_SELECTOR_RE", re.compile(r"^custom:([1-9][0-9]*)$"))

    assert worker.parse_guacamole_selector("custom:9") == 9


def test_safe_connection_response_contract_preserves_public_fields_and_selector():
    connection = {
        "id": 7,
        "selector": "guac:id:7",
        "name": "RDP Lab",
        "protocol": "rdp",
        "hostname": "lab-01",
        "port": "3389",
        "users": ["should-not-leak"],
    }

    assert worker.safe_connection_response(connection) == {
        "id": 7,
        "selector": "guac:id:7",
        "name": "RDP Lab",
        "protocol": "rdp",
        "hostname": "lab-01",
        "port": "3389",
        "warnings": [],
    }


def test_safe_connection_response_contract_builds_selector_when_missing():
    assert worker.safe_connection_response({"id": 8, "name": "Other"}) == {
        "id": 8,
        "selector": "guac:id:8",
        "name": "Other",
        "protocol": None,
        "hostname": None,
        "port": None,
        "warnings": [],
    }
