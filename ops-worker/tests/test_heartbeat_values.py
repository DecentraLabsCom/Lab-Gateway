import re

import heartbeat_values


MAC_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")


def _normalize(value):
    return heartbeat_values.normalize_mac(value, mac_pattern=MAC_PATTERN)


def test_heartbeat_values_normalize_mac_and_boolean_flags():
    assert _normalize("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert _normalize("not-a-mac") == ""
    assert heartbeat_values.parse_boolish("enabled") is True
    assert heartbeat_values.parse_boolish("off") is False


def test_heartbeat_values_extract_and_select_best_wake_adapter():
    heartbeat = {
        "status": {
            "wake": {
                "nicPower": [
                    {"macAddress": "AA-BB-CC-DD-EE-FF", "status": "Up"},
                    {
                        "macAddress": "00-11-22-33-44-55",
                        "status": "Up",
                        "wolReady": True,
                        "wakeArmed": True,
                    },
                ]
            }
        }
    }

    candidates = heartbeat_values.extract_nic_candidates_from_heartbeat(
        heartbeat,
        normalize_mac_fn=_normalize,
        parse_boolish_fn=heartbeat_values.parse_boolish,
    )

    assert len(candidates) == 2
    assert heartbeat_values.choose_wol_mac(candidates)["mac"] == "00:11:22:33:44:55"
    assert heartbeat_values.suggest_mac_from_heartbeat(
        heartbeat,
        normalize_mac_fn=_normalize,
        parse_boolish_fn=heartbeat_values.parse_boolish,
    )["source"] == "status.wake.nicPower"
