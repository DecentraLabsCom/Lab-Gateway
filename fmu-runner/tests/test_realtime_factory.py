from unittest.mock import MagicMock

from realtime_factory import build_realtime_manager


def _dependencies():
    return {
        "logger": MagicMock(),
        "verify_jwt_token": MagicMock(),
        "enforce_fmu_claim": MagicMock(),
        "resolve_fmu_path": MagicMock(),
        "get_claim_lab_id": MagicMock(),
        "normalize_lab_id": MagicMock(),
        "coerce_epoch_seconds": MagicMock(),
        "acquire_slot": MagicMock(),
        "release_slot": MagicMock(),
        "redeem_session_ticket": MagicMock(),
        "issue_session_ticket": MagicMock(),
        "confirm_session_started": MagicMock(),
        "ws_session_queue_size": 64,
        "ws_heartbeat_seconds": 15.0,
        "ws_expiring_notice_seconds": 60,
        "ws_attach_grace_seconds": 120,
        "ws_cleanup_seconds": 15.0,
        "internal_ws_token": "internal-token",
        "ws_create_rate_limit_per_minute": 30,
    }


def test_realtime_factory_builds_local_manager_with_exact_contract():
    dependencies = _dependencies()
    local_factory = MagicMock(return_value="local-manager")
    station_factory = MagicMock()
    backend = MagicMock(supports_local_execution=True, mode="local")

    manager = build_realtime_manager(
        backend=backend,
        local_realtime_enabled=True,
        local_manager_factory=local_factory,
        station_manager_factory=station_factory,
        unsupported_manager_factory=MagicMock(),
        **dependencies,
    )

    assert manager == "local-manager"
    local_factory.assert_called_once_with(
        logger=dependencies["logger"],
        verify_jwt_token=dependencies["verify_jwt_token"],
        enforce_fmu_claim=dependencies["enforce_fmu_claim"],
        resolve_fmu_path=dependencies["resolve_fmu_path"],
        get_claim_lab_id=dependencies["get_claim_lab_id"],
        normalize_lab_id=dependencies["normalize_lab_id"],
        coerce_epoch_seconds=dependencies["coerce_epoch_seconds"],
        acquire_slot=dependencies["acquire_slot"],
        release_slot=dependencies["release_slot"],
        redeem_session_ticket=dependencies["redeem_session_ticket"],
        issue_session_ticket=dependencies["issue_session_ticket"],
        confirm_session_started=dependencies["confirm_session_started"],
        ws_session_queue_size=64,
        ws_heartbeat_seconds=15.0,
        ws_expiring_notice_seconds=60,
        ws_attach_grace_seconds=120,
        ws_cleanup_seconds=15.0,
        internal_ws_token="internal-token",
        ws_create_rate_limit_per_minute=30,
    )
    station_factory.assert_not_called()


def test_realtime_factory_builds_station_proxy_with_exact_contract():
    dependencies = _dependencies()
    local_factory = MagicMock()
    station_factory = MagicMock(return_value="station-manager")
    backend = MagicMock(supports_local_execution=False, mode="station")

    manager = build_realtime_manager(
        backend=backend,
        local_realtime_enabled=False,
        local_manager_factory=local_factory,
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
    local_factory.assert_not_called()


def test_realtime_factory_falls_back_to_unsupported_manager_with_reason():
    dependencies = _dependencies()
    unsupported_factory = MagicMock(return_value="unsupported-manager")
    backend = MagicMock(supports_local_execution=True, mode="local")

    manager = build_realtime_manager(
        backend=backend,
        local_realtime_enabled=False,
        local_manager_factory=MagicMock(),
        station_manager_factory=MagicMock(),
        unsupported_manager_factory=unsupported_factory,
        **dependencies,
    )

    assert manager == "unsupported-manager"
    unsupported_factory.assert_called_once_with(
        reason=(
            "Local realtime FMU execution is disabled by default because native "
            "doStep calls cannot be force-terminated inside the ASGI process. "
            "Use FMU_BACKEND_MODE=station in production, or explicitly set "
            "FMU_LOCAL_REALTIME_ENABLED=true only for isolated development."
        )
    )
