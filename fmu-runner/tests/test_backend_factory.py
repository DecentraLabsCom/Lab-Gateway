from unittest.mock import MagicMock

from backend_factory import build_fmu_backend


def _dependencies():
    return {
        "health_loader": MagicMock(return_value={"status": "UP"}),
        "model_metadata_loader": MagicMock(),
        "list_loader": MagicMock(),
        "station_backend_factory": MagicMock(return_value="station-backend"),
        "local_backend_factory": MagicMock(return_value="local-backend"),
        "logger": MagicMock(),
    }


def test_backend_factory_preserves_station_selection_and_constructor_contract():
    dependencies = _dependencies()

    backend = build_fmu_backend(
        mode="station",
        local_dev_mode=False,
        station_base_url="https://station.example/",
        station_internal_token="station-token",
        station_request_timeout=12.5,
        **dependencies,
    )

    assert backend == "station-backend"
    dependencies["station_backend_factory"].assert_called_once_with(
        base_url="https://station.example/",
        internal_token="station-token",
        request_timeout=12.5,
    )
    dependencies["local_backend_factory"].assert_not_called()
    dependencies["logger"].info.assert_called_once_with("FMU backend mode selected: station")


def test_backend_factory_disables_local_execution_without_explicit_dev_mode():
    dependencies = _dependencies()

    backend = build_fmu_backend(
        mode="local",
        local_dev_mode=False,
        station_base_url="",
        station_internal_token="",
        station_request_timeout=10.0,
        **dependencies,
    )

    assert backend == "local-backend"
    dependencies["local_backend_factory"].assert_called_once_with(
        health_loader=dependencies["health_loader"],
        model_metadata_loader=dependencies["model_metadata_loader"],
        list_loader=dependencies["list_loader"],
        allow_execution=False,
    )
    dependencies["logger"].error.assert_called_once_with(
        "FMU_BACKEND_MODE=local requires FMU_LOCAL_DEV_MODE=true; "
        "native FMU execution is disabled",
    )


def test_backend_factory_unknown_mode_falls_back_to_disabled_local_backend():
    dependencies = _dependencies()

    build_fmu_backend(
        mode="unexpected",
        local_dev_mode=True,
        station_base_url="",
        station_internal_token="",
        station_request_timeout=10.0,
        **dependencies,
    )

    dependencies["logger"].error.assert_called_once_with(
        "Unknown FMU_BACKEND_MODE=%s; local execution remains disabled",
        "unexpected",
    )
    dependencies["local_backend_factory"].assert_called_once()
