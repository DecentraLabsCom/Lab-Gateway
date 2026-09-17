"""Contracts for the optional routed Station LAN overlay."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "docker-compose.wol.yml"
ENV_EXAMPLE = ROOT / ".env.example"
CONFIGURATION = ROOT / "docs" / "reference" / "configuration.md"


def test_wol_overlay_supports_optional_default_gateway():
    overlay = OVERLAY.read_text(encoding="utf-8")

    assert "driver: macvlan" in overlay
    assert "parent: ${WOL_LAN_PARENT:?WOL_LAN_PARENT must be configured}" in overlay
    assert "subnet: ${WOL_LAN_SUBNET:?WOL_LAN_SUBNET must be configured}" in overlay
    assert "ip_range: ${WOL_LAN_IP_RANGE:?WOL_LAN_IP_RANGE must be configured}" in overlay
    assert "gateway: ${WOL_LAN_GATEWAY:-}" in overlay


def test_both_station_lan_gateway_modes_are_documented():
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    configuration = CONFIGURATION.read_text(encoding="utf-8")

    assert "Leave WOL_LAN_GATEWAY empty" in env_example
    assert "directly connected route" in configuration
    assert "WOL_LAN_GATEWAY" in configuration
