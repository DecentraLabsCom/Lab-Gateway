from heartbeat_readiness import capability_ready


def test_capability_ready_prefers_top_level_readiness_and_supports_legacy_heartbeat():
    heartbeat = {
        "ready": False,
        "readiness": {"physicalLab": {"ready": True}},
    }

    assert capability_ready(heartbeat, "physicalLab") is True
    assert capability_ready({"ready": True}, "physicalLab") is True
    assert capability_ready({"ready": False}, "physicalLab") is False


def test_capability_ready_reads_station_nested_readiness_as_transition_fallback():
    heartbeat = {
        "ready": False,
        "status": {"readiness": {"fmu": {"ready": True}}},
    }

    assert capability_ready(heartbeat, "fmu") is True
