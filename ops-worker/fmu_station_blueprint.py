"""Flask boundary for the single FMU Station link/release flow."""

from collections.abc import Callable, Mapping
from typing import Any

from flask import Blueprint, jsonify, request

from fmu_station_enrollment import (
    FmuStationConfig,
    FmuStationEnrollmentError,
    enroll_fmu_station,
    public_station_status,
    release_fmu_station,
)


def create_fmu_station_blueprint(
    *,
    get_config: Callable[[], FmuStationConfig],
    get_hosts: Callable[[], list[Mapping[str, Any]]],
    get_runner_health: Callable[[], Mapping[str, Any]],
    run_remote_powershell: Callable[..., Any],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the protected Ops API for the Gateway's one FMU Station."""
    blueprint = Blueprint("fmu_station", __name__)

    @blueprint.get("/api/fmu/station")
    def api_get_fmu_station():
        return jsonify(
            public_station_status(
                get_config(),
                get_hosts(),
                runner_health=get_runner_health(),
            )
        )

    @blueprint.post("/api/fmu/station/enroll")
    def api_enroll_fmu_station():
        payload = request.get_json(force=True, silent=True) or {}
        try:
            result = enroll_fmu_station(
                payload if isinstance(payload, Mapping) else {},
                config=get_config(),
                hosts=get_hosts(),
                run_remote_powershell=run_remote_powershell,
            )
        except FmuStationEnrollmentError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
        except Exception as exc:  # pylint: disable=broad-except
            return internal_error_response("FMU Station enrollment failed", exc)
        return jsonify(result)

    @blueprint.post("/api/fmu/station/release")
    def api_release_fmu_station():
        payload = request.get_json(force=True, silent=True) or {}
        try:
            result = release_fmu_station(
                payload if isinstance(payload, Mapping) else {},
                config=get_config(),
                hosts=get_hosts(),
                run_remote_powershell=run_remote_powershell,
            )
        except FmuStationEnrollmentError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
        except Exception as exc:  # pylint: disable=broad-except
            return internal_error_response("FMU Station release failed", exc)
        return jsonify(result)

    return blueprint


__all__ = ["create_fmu_station_blueprint"]
