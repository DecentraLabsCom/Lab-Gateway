from flask import Flask, jsonify

from fmu_station_blueprint import create_fmu_station_blueprint
from fmu_station_enrollment import FmuStationConfig


TOKEN = "fmu_" + "b" * 64
HOSTS = [{"name": "lab-ws-01", "address": "192.168.1.50"}]


def _blueprint(**overrides):
    providers = {
        "get_config": lambda: FmuStationConfig(
            backend_mode="station",
            base_url="http://192.168.1.50:8091",
            configured_host="",
            internal_token=TOKEN,
        ),
        "get_hosts": lambda: HOSTS,
        "get_runner_health": lambda: {
            "status": "UP",
            "checks": {"stationHealth": True, "stationAuthentication": True},
        },
        "run_remote_powershell": lambda **_kwargs: None,
        "internal_error_response": lambda message, _exc: (jsonify({"error": message}), 500),
    }
    providers.update(overrides)
    return create_fmu_station_blueprint(**providers)


def test_fmu_station_routes_are_owned_by_the_blueprint():
    app = Flask("fmu-station-blueprint-contract")
    app.register_blueprint(_blueprint())

    routes = {
        rule.rule: rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/fmu/station")
    }

    assert routes["/api/fmu/station"].methods == {"GET", "HEAD", "OPTIONS"}
    assert routes["/api/fmu/station/enroll"].methods == {"POST", "OPTIONS"}
    assert routes["/api/fmu/station/release"].methods == {"POST", "OPTIONS"}


def test_status_is_safe_and_enrollment_returns_no_secret():
    app = Flask("fmu-station-blueprint-payload-contract")
    calls = []
    app.register_blueprint(_blueprint(run_remote_powershell=lambda **kwargs: calls.append(kwargs)))
    client = app.test_client()

    status = client.get("/api/fmu/station")
    assert status.status_code == 200
    assert status.json["singleStationPerGateway"] is True
    assert "internalToken" not in status.json
    assert TOKEN not in status.get_data(as_text=True)

    enrolled = client.post("/api/fmu/station/enroll", json={"host": "lab-ws-01"})
    assert enrolled.status_code == 200
    assert enrolled.json == {
        "address": "192.168.1.50",
        "enrolled": True,
        "host": "lab-ws-01",
        "restartRequested": True,
    }
    assert calls and TOKEN not in calls[0]["script"]

    released = client.post("/api/fmu/station/release", json={"host": "lab-ws-01"})
    assert released.status_code == 200
    assert released.json == {
        "address": "192.168.1.50",
        "host": "lab-ws-01",
        "released": True,
        "restartRequested": True,
    }
    assert "$null" in calls[1]["script"]


def test_enrollment_rejects_unregistered_host_without_remote_call():
    app = Flask("fmu-station-blueprint-validation-contract")
    calls = []
    app.register_blueprint(_blueprint(run_remote_powershell=lambda **kwargs: calls.append(kwargs)))

    response = app.test_client().post(
        "/api/fmu/station/enroll",
        json={"host": "unknown"},
    )

    assert response.status_code == 404
    assert response.json["code"] == "FMU_STATION_HOST_NOT_FOUND"
    assert calls == []
