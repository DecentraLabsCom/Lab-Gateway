"""Contracts for the direct, gateway-less Station LAN overlay."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "docker-compose.wol.yml"
ENV_EXAMPLE = ROOT / ".env.example"
CONFIGURATION = ROOT / "docs" / "reference" / "configuration.md"


def test_wol_overlay_does_not_require_a_default_gateway():
    overlay = OVERLAY.read_text(encoding="utf-8")

    assert "driver: macvlan" in overlay
    assert "parent: ${WOL_LAN_PARENT:?WOL_LAN_PARENT must be configured}" in overlay
    assert "subnet: ${WOL_LAN_SUBNET:?WOL_LAN_SUBNET must be configured}" in overlay
    assert "ip_range: ${WOL_LAN_IP_RANGE:?WOL_LAN_IP_RANGE must be configured}" in overlay
    assert "\n          gateway:" not in overlay
    assert "WOL_LAN_GATEWAY" not in overlay


def test_gatewayless_wol_configuration_is_documented():
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    configuration = CONFIGURATION.read_text(encoding="utf-8")

    assert "does not install a default gateway" in env_example
    assert "directly connected route" in configuration
    assert "WOL_LAN_GATEWAY" not in configuration
