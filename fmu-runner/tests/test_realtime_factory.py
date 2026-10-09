from unittest.mock import MagicMock

from realtime_factory import build_realtime_manager


def _dependencies():
    return {
        "logger": MagicMock(),
        "verify_jwt_token": MagicMock(),
        "enforce_fmu_claim": MagicMock(),
        "get_claim_lab_id": MagicMock(),
        "normalize_lab_id": MagicMock(),
        "coerce_epoch_seconds": MagicMock(),
        "redeem_session_ticket": MagicMock(),
        "issue_session_ticket": MagicMock(),
        "confirm_session_started": MagicMock(),
        "ws_cleanup_seconds": 15.0,
        "internal_ws_token": "internal-token",
        "ws_create_rate_limit_per_minute": 30,
    }


def test_realtime_factory_builds_remote_station_proxy():
    dependencies = _dependencies()
    station_factory = MagicMock(return_value="station-manager")
    backend = MagicMock(mode="station")

    manager = build_realtime_manager(
        backend=backend,
        station_manager_factory=station_factory,
        unsupported_manager_factory=MagicMock(),
        **dependencies,
    )

    assert manager == "station-manager"
    station_factory.assert_called_once_with(
        logger=dependencies["logger"],
        station_backend=backend,
        verify_jwt_token=dependencies["verify_jwt_token"],
        enforce_fmu_claim=dependencies["enforce_fmu_claim"],
        get_claim_lab_id=dependencies["get_claim_lab_id"],
        normalize_lab_id=dependencies["normalize_lab_id"],
        coerce_epoch_seconds=dependencies["coerce_epoch_seconds"],
        redeem_session_ticket=dependencies["redeem_session_ticket"],
        issue_session_ticket=dependencies["issue_session_ticket"],
        confirm_session_started=dependencies["confirm_session_started"],
        ws_cleanup_seconds=15.0,
        internal_ws_token="internal-token",
        ws_create_rate_limit_per_minute=30,
    )


def test_realtime_factory_disables_sessions_without_remote_executor():
    dependencies = _dependencies()
    unsupported_factory = MagicMock(return_value="unsupported-manager")
    backend = MagicMock(mode="local")

    manager = build_realtime_manager(
        backend=backend,
        station_manager_factory=MagicMock(),
        unsupported_manager_factory=unsupported_factory,
        **dependencies,
    )

    assert manager == "unsupported-manager"
    unsupported_factory.assert_called_once_with(
        reason="Realtime FMU sessions require a remote Executor; mode is local.",
    )
