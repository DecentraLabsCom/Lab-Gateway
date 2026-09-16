import json
import os
import sys
from typing import Any, Dict, List

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.base import PowerDriver
from power.drivers.mock import MockPowerDriver
from power.models import LabPowerPolicy, PowerCapabilities, PowerController, PowerOutlet, ValidationError
from power.persistence import PowerOperationStore
from power.registry import PowerRegistry, RegisteredController
from power.service import PowerRuntime
import worker


class CountingPowerDriver(PowerDriver):
    capabilities = PowerCapabilities()

    def __init__(self):
        self.list_calls = 0
        self.discover_calls = 0

    def list_outlets(self) -> List[Dict[str, Any]]:
        self.list_calls += 1
        return [{"outlet": "1", "name": "Bench outlet", "state": "off"}]

    def discover(self) -> Dict[str, Any]:
        self.discover_calls += 1
        return {
            "reachable": True,
            "driver": "test",
            "controllerId": "counting-1",
            "profile": "test",
            "outletCount": 1,
        }

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        raise NotImplementedError

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        raise NotImplementedError


class LiveConfigurationDriver(PowerDriver):
    capabilities = PowerCapabilities(per_outlet_switching=True, read_back_state=True)

    def read_configuration(self) -> Dict[str, Any]:
        return {
            "writable": True,
            "fields": ["name"],
            "outlets": [
                {"outlet": "1", "name": "PLC", "state": "off", "deviceConfigFields": ["name"]},
                {"outlet": "4", "name": "HMI", "state": "on", "deviceConfigFields": ["name"]},
            ],
        }

    def apply_configuration(self, configuration):
        return self.read_configuration()

    def list_outlets(self):
        return self.read_configuration()["outlets"]

    def discover(self):
        return {"reachable": True, "driver": "live-test", "outletCount": 2}

    def get_outlet_state(self, outlet_id):
        return {"outlet": outlet_id, "state": "off"}

    def set_outlet_state(self, outlet_id, state, timeout_seconds=20):
        return {"outlet": outlet_id, "state": state, "success": True}

    def cycle_outlet(self, outlet_id, off_seconds=10, timeout_seconds=30):
        return {"outlet": outlet_id, "state": "on", "success": True}


def mock_driver(runtime: PowerRuntime) -> MockPowerDriver:
    driver = runtime.registry.get("mock-lab-01").driver
    assert isinstance(driver, MockPowerDriver)
    return driver


def build_counting_status_runtime(*, status_cache_ttl_seconds=60):
    driver = CountingPowerDriver()
    controller = RegisteredController(
        PowerController("counting-1", "Counting controller", "test"),
        driver,
        {"1": PowerOutlet("counting-1", "1", logical_name="Bench outlet")},
    )
    runtime = PowerRuntime(
        PowerRegistry([controller]),
        {},
        status_cache_ttl_seconds=status_cache_ttl_seconds,
    )
    return runtime, driver


def build_runtime(*, record_operation=None, sleep_fn=None, operation_store=None):
    return PowerRuntime.from_config(
        {
            "controllers": [
                {
                    "id": "mock-lab-01",
                    "name": "Mock lab controller",
                    "driver": "mock",
                    "config": {"outlets": ["1", "2"]},
                }
            ],
            "outlets": [
                {
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "logicalName": "plc",
                },
                {
                    "controllerId": "mock-lab-01",
                    "outlet": "2",
                    "logicalName": "hmi",
                },
            ],
            "policies": [
                {
                    "id": "policy-1",
                    "labId": "lab-1",
                    "policyName": "PLC default",
                    "steps": [
                        {
                            "phase": "pre_start",
                            "sequence": 20,
                            "controllerId": "mock-lab-01",
                            "outlet": "2",
                            "action": "on",
                            "readBackRequired": True,
                        },
                        {
                            "phase": "pre_start",
                            "sequence": 10,
                            "controllerId": "mock-lab-01",
                            "outlet": "1",
                            "action": "on",
                            "readBackRequired": True,
                        },
                        {
                            "phase": "post_end",
                            "sequence": 10,
                            "controllerId": "mock-lab-01",
                            "outlet": "2",
                            "action": "off",
                        },
                        {
                            "phase": "post_end",
                            "sequence": 20,
                            "controllerId": "mock-lab-01",
                            "outlet": "1",
                            "action": "off",
                        },
                    ],
                }
            ],
        },
        record_operation=record_operation,
        sleep_fn=sleep_fn,
        operation_store=operation_store,
    )


def test_legacy_policy_steps_are_sorted_and_reject_duplicate_phase_sequence():
    policy = LabPowerPolicy.from_mapping(
        {
            "labId": "lab-1",
            "policyName": "ordered",
            "steps": [
                {
                    "phase": "pre_start",
                    "sequence": 20,
                    "controllerId": "controller",
                    "outlet": "2",
                    "action": "on",
                },
                {
                    "phase": "pre_start",
                    "sequence": 10,
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "on",
                },
            ],
        }
    )

    assert [step.sequence for step in policy.steps_for_phase("pre_start")] == [10, 20]

    with pytest.raises(ValidationError, match="duplicate sequence"):
        LabPowerPolicy.from_mapping(
            {
                "labId": "lab-1",
                "policyName": "invalid",
                "steps": [
                    {
                        "phase": "pre_start",
                        "sequence": 10,
                        "controllerId": "controller",
                        "outlet": "1",
                        "action": "on",
                    },
                    {
                        "phase": "pre_start",
                        "sequence": 10,
                        "controllerId": "controller",
                        "outlet": "2",
                        "action": "off",
                    },
                ],
            }
        )


def test_policy_steps_follow_ui_order_without_exposing_sequence():
    policy = LabPowerPolicy.from_mapping(
        {
            "labId": "lab-1",
            "policyName": "ordered",
            "steps": [
                {
                    "phase": "pre_start",
                    "controllerId": "controller",
                    "outlet": "2",
                    "action": "on",
                },
                {
                    "phase": "pre_start",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "on",
                },
                {
                    "phase": "end",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "off",
                },
            ],
        }
    )

    assert [step.outlet for step in policy.steps_for_phase("pre_start")] == ["2", "1"]
    assert [step.sequence for step in policy.steps_for_phase("pre_start")] == [10, 20]
    serialized = policy.to_dict()
    assert [step["outlet"] for step in serialized["steps"]] == ["2", "1", "1"]
    assert all("sequence" not in step for step in serialized["steps"])
    assert len({step["id"] for step in serialized["steps"]}) == 3

    reloaded = LabPowerPolicy.from_mapping(serialized)
    assert [step.outlet for step in reloaded.steps_for_phase("pre_start")] == ["2", "1"]
    assert [step.step_id for step in reloaded.steps] == [step["id"] for step in serialized["steps"]]


def test_policy_action_is_the_only_state_target_and_step_label_is_explicit():
    policy = LabPowerPolicy.from_mapping(
        {
            "labId": "lab-1",
            "policyName": "targets",
            "steps": [
                {
                    "phase": "start",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "on",
                    "stepLabel": "PLC boot",
                },
                {
                    "phase": "end",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "cycle",
                    "offSeconds": 15,
                },
            ],
        }
    )

    assert not hasattr(policy.steps[0], "desired_state")
    serialized = policy.to_dict()
    assert serialized["steps"][0]["stepLabel"] == "PLC boot"
    assert "desiredState" not in serialized["steps"][0]
    assert "offSeconds" not in serialized["steps"][0]
    assert serialized["steps"][1]["offSeconds"] == 15


def test_executor_runs_phases_in_order_and_is_idempotent():
    operations = []
    runtime = build_runtime(record_operation=operations.append)

    first = runtime.execute_policy("lab-1", "reservation-1", "pre_start", actor="test")
    second = runtime.execute_policy("lab-1", "reservation-1", "pre_start", actor="test")

    assert first["success"] is True
    assert [step["outlet"] for step in first["steps"]] == ["1", "2"]
    assert [step["status"] for step in second["steps"]] == [
        "skipped_already_completed",
        "skipped_already_completed",
    ]
    assert mock_driver(runtime).states == {"1": "on", "2": "on"}
    assert len(operations) == 2


def test_required_failure_stops_phase_but_optional_failure_continues():
    runtime = build_runtime()
    driver = mock_driver(runtime)
    driver.fail_action("on", outlet="1")

    result = runtime.execute_policy("lab-1", "reservation-required", "pre_start", actor="test")
    assert result["success"] is False
    assert result["steps"][0]["status"] == "failed"
    assert len(result["steps"]) == 1

    optional_policy = LabPowerPolicy.from_mapping(
        {
            "labId": "lab-optional",
            "policyName": "optional",
            "steps": [
                {
                    "phase": "pre_start",
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "action": "on",
                    "required": False,
                },
                {
                    "phase": "pre_start",
                    "sequence": 20,
                    "controllerId": "mock-lab-01",
                    "outlet": "2",
                    "action": "on",
                },
            ],
        }
    )
    runtime.policies["lab-optional"] = optional_policy

    result = runtime.execute_policy("lab-optional", "reservation-optional", "pre_start", actor="test")
    assert result["success"] is True
    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][1]["success"] is True


def test_mock_driver_rejects_protected_outlet_without_maintenance_override():
    runtime = build_runtime()
    runtime.registry.get("mock-lab-01").outlets["1"].protected = True

    with pytest.raises(PermissionError, match="protected"):
        runtime.execute_manual(
            controller_id="mock-lab-01",
            outlet_id="1",
            action="off",
            actor="operator",
            idempotency_key="manual-1",
        )

    result = runtime.execute_manual(
        controller_id="mock-lab-01",
        outlet_id="1",
        action="off",
        actor="maintenance",
        idempotency_key="manual-2",
        allow_protected=True,
        maintenance=True,
    )
    assert result["success"] is True


def test_power_api_lists_controllers_runs_commands_and_executes_lab_phases(client, monkeypatch):
    runtime = build_runtime()
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    controllers = client.get("/api/power/controllers")
    assert controllers.status_code == 200
    assert controllers.json["controllers"][0]["id"] == "mock-lab-01"
    assert controllers.json["controllers"][0]["outlets"][0]["state"] == "unknown"

    statuses = client.get("/api/power/controllers/status")
    assert statuses.status_code == 200
    assert statuses.json["controllers"][0]["discovery"]["reachable"] is True
    assert statuses.json["controllers"][0]["outlets"][0]["state"] == "off"

    command = client.post(
        "/api/power/controllers/mock-lab-01/outlets/1/commands",
        json={
            "command": "set_state",
            "state": "on",
            "actor": "lab-manager",
            "reason": "manual-test",
            "idempotencyKey": "manual-test-1",
        },
    )
    assert command.status_code == 200
    assert command.json["operation"]["status"] == "completed"

    start = client.post(
        "/api/labs/lab-1/power/start",
        json={"reservationId": "reservation-api-1", "actor": "scheduler"},
    )
    assert start.status_code == 200
    assert start.json["success"] is True
    assert [step["outlet"] for step in start.json["steps"]] == ["1", "2"]

    end = client.post(
        "/api/labs/lab-1/power/end",
        json={"reservationId": "reservation-api-1", "actor": "scheduler"},
    )
    assert end.status_code == 200
    assert end.json["success"] is True
    assert mock_driver(runtime).states == {"1": "off", "2": "off"}


def test_power_runtime_separates_catalog_from_cached_status():
    runtime, driver = build_counting_status_runtime()

    catalog = runtime.describe_controllers()

    assert catalog[0]["name"] == "Counting controller"
    assert catalog[0]["discovery"] == {}
    assert catalog[0]["outlets"][0]["state"] == "unknown"
    assert driver.list_calls == 0
    assert driver.discover_calls == 0

    first_status = runtime.describe_controller_statuses()
    second_status = runtime.describe_controller_statuses()
    forced_status = runtime.describe_controller_statuses(force_refresh=True)

    assert first_status[0]["discovery"]["reachable"] is True
    assert first_status[0]["outlets"][0]["state"] == "off"
    assert second_status == first_status
    assert forced_status == first_status
    assert driver.list_calls == 2
    assert driver.discover_calls == 2


def test_registry_uses_live_outputs_without_a_duplicated_local_catalog():
    driver = LiveConfigurationDriver()
    controller = RegisteredController(
        PowerController("live-1", "Live controller", "live-test"),
        driver,
        {},
    )
    registry = PowerRegistry([controller])

    description = registry.public_description(controller)

    assert [outlet["outlet"] for outlet in description["outlets"]] == ["1", "4"]
    assert [outlet["deviceName"] for outlet in description["outlets"]] == ["PLC", "HMI"]
    assert registry.get_outlet("live-1", "4")[1].outlet_key == "4"


def test_power_controller_status_api_can_bypass_status_cache(client, monkeypatch):
    runtime, driver = build_counting_status_runtime()
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    first = client.get("/api/power/controllers/status")
    cached = client.get("/api/power/controllers/status")
    refreshed = client.get("/api/power/controllers/status?refresh=true")

    assert first.status_code == 200
    assert cached.status_code == 200
    assert refreshed.status_code == 200
    assert driver.list_calls == 2
    assert driver.discover_calls == 2


def test_power_controller_api_creates_and_updates_provider_catalog(client, tmp_path, monkeypatch):
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(
        json.dumps({
            "controllers": [],
            "outlets": [{
                "controllerId": "legacy-controller",
                "outlet": "9",
                "logicalName": "legacy",
                "critical": True,
            }],
            "policies": [],
        }),
        encoding="utf-8",
    )
    runtime = PowerRuntime.from_path(
        str(config_path),
        credential_resolver=lambda _reference: {"version": "v2c", "community": "private"},
    )
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    created = client.post(
        "/api/power/controllers",
        json={
            "id": "pdu-lab-01",
            "name": "Bench PDU",
            "driver": "mock",
            "enabled": True,
            "config": {"timeoutSeconds": 3},
            "outlets": [
                {"outlet": "1", "logicalName": "PLC"},
            ],
        },
    )
    assert created.status_code == 201
    assert created.json["controller"]["id"] == "pdu-lab-01"
    assert created.json["controller"]["outlets"][0]["logicalName"] == "PLC"
    assert "critical" not in created.json["controller"]["outlets"][0]

    updated = client.put(
        "/api/power/controllers/pdu-lab-01",
        json={
            "id": "pdu-lab-01",
            "name": "Bench PDU Updated",
            "driver": "mock",
            "enabled": False,
            "config": {"timeoutSeconds": 4},
            "outlets": [
                {"outlet": "1", "logicalName": "PLC"},
                {"outlet": "2", "logicalName": "HMI"},
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json["controller"]["name"] == "Bench PDU Updated"
    assert updated.json["controller"]["enabled"] is False
    assert [outlet["outlet"] for outlet in updated.json["controller"]["outlets"]] == ["1", "2"]
    assert all("critical" not in outlet for outlet in updated.json["controller"]["outlets"])
    assert runtime.describe_controllers()[0]["name"] == "Bench PDU Updated"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["controllers"][0]["name"] == "Bench PDU Updated"
    assert [outlet["outlet"] for outlet in persisted["outlets"]] == ["9", "1", "2"]
    assert all("critical" not in outlet for outlet in persisted["outlets"])


def test_power_controller_update_synchronizes_device_configuration_before_persisting(tmp_path, monkeypatch):
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(json.dumps({"controllers": [], "outlets": [], "policies": []}), encoding="utf-8")
    runtime = PowerRuntime.from_path(
        str(config_path),
        credential_resolver=lambda _reference: {"version": "v2c", "community": "private"},
    )
    original_from_config = PowerRuntime.from_config.__func__
    applied = []

    def build_candidate(cls, config, **kwargs):
        candidate = original_from_config(cls, config, **kwargs)
        candidate.registry.get("pdu-1").driver.apply_configuration = applied.append
        return candidate

    monkeypatch.setattr(PowerRuntime, "from_config", classmethod(build_candidate))

    updated = runtime.update_controller({
        "id": "pdu-1",
        "name": "APC PDU",
        "driver": "apc-powernet-snmp",
        "host": "192.0.2.20",
        "credentialRef": "pdu-1",
        "config": {"profile": "legacy"},
        "outlets": [],
        "deviceConfiguration": {
            "outlets": [{
                "outlet": "1",
                "name": "PLC",
                "config": {"powerOnDelaySeconds": 5},
            }],
        },
    })

    assert updated["id"] == "pdu-1"
    assert applied == [{
        "outlets": [{
            "outlet": "1",
            "name": "PLC",
            "config": {"powerOnDelaySeconds": 5},
        }],
    }]
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "deviceConfiguration" not in persisted["controllers"][0]
    assert persisted["outlets"] == []


def test_power_controller_api_rejects_secret_config_without_changing_catalog(client, tmp_path, monkeypatch):
    config_path = tmp_path / "power-controllers.json"
    original = {"controllers": [], "outlets": [], "policies": []}
    config_path.write_text(json.dumps(original), encoding="utf-8")
    runtime = PowerRuntime.from_path(str(config_path))
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    response = client.post(
        "/api/power/controllers",
        json={
            "id": "pdu-lab-01",
            "name": "Bench PDU",
            "driver": "mock",
            "config": {"community": "do-not-store-this"},
            "outlets": [{"outlet": "1"}],
        },
    )

    assert response.status_code == 400
    assert response.json["error"] == "Power controller configuration is invalid"
    assert "do-not-store-this" not in response.get_data(as_text=True)
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_power_api_requires_reservation_and_rejects_unknown_controller(client, monkeypatch):
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", build_runtime())

    missing_reservation = client.post("/api/labs/lab-1/power/start", json={})
    assert missing_reservation.status_code == 400

    unknown = client.post(
        "/api/power/controllers/unknown/outlets/1/commands",
        json={"command": "set_state", "state": "on", "idempotencyKey": "unknown-1"},
    )
    assert unknown.status_code == 404
    assert unknown.json["error"] == "Power controller or outlet was not found"


def test_power_api_sanitizes_exception_details(client, monkeypatch):
    runtime = build_runtime()
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    invalid_policy = client.put(
        "/api/power/policies/lab-1",
        json={
            "policyName": "invalid",
            "steps": [
                {
                    "phase": "pre_start",
                    "sequence": 10,
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "action": "on",
                },
                {
                    "phase": "pre_start",
                    "sequence": 10,
                    "controllerId": "mock-lab-01",
                    "outlet": "2",
                    "action": "off",
                },
            ],
        },
    )
    assert invalid_policy.status_code == 400
    assert invalid_policy.json["error"] == "Power policy is invalid"
    assert "duplicate sequence" not in invalid_policy.get_data(as_text=True)

    runtime.registry.get("mock-lab-01").outlets["1"].protected = True
    forbidden = client.post(
        "/api/power/controllers/mock-lab-01/outlets/1/commands",
        json={"command": "off", "idempotencyKey": "protected-1"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json["error"] == "Power operation is not permitted"
    assert "protected outlet" not in forbidden.get_data(as_text=True)

    def raise_validation_error(*_args, **_kwargs):
        raise ValidationError("internal phase details")

    monkeypatch.setattr(runtime, "execute_policy", raise_validation_error)
    phase = client.post(
        "/api/labs/lab-1/power/start",
        json={"reservationId": "reservation-1"},
    )
    assert phase.status_code == 422
    assert phase.json["error"] == "Power phase request is invalid"
    assert "internal phase details" not in phase.get_data(as_text=True)


def test_power_operation_is_projected_to_reservation_timeline(db_engine):
    runtime = build_runtime(record_operation=worker._record_power_operation)

    result = runtime.execute_policy("lab-1", "reservation-db-1", "pre_start", actor="scheduler")

    assert result["success"] is True
    rows = db_engine.connect().execute(
        worker.text(
            "SELECT action, status, success, host, lab_id "
            "FROM reservation_operations WHERE reservation_id = :reservation_id "
            "ORDER BY id"
        ),
        {"reservation_id": "reservation-db-1"},
    ).mappings().all()
    assert [row["action"] for row in rows] == ["power:on", "power:on"]
    assert all(row["success"] for row in rows)
    assert {row["host"] for row in rows} == {"mock-lab-01"}
    assert {row["lab_id"] for row in rows} == {"lab-1"}


def test_manual_power_operation_uses_bounded_timeline_reservation_id(db_engine):
    runtime = build_runtime(record_operation=worker._record_power_operation)

    result = runtime.execute_manual(
        controller_id="mock-lab-01",
        outlet_id="1",
        action="on",
        actor="lab-manager",
        idempotency_key="x" * 128,
    )

    assert result["success"] is True
    row = db_engine.connect().execute(
        worker.text(
            "SELECT reservation_id, action FROM reservation_operations "
            "WHERE action = 'power:on' ORDER BY id DESC LIMIT 1"
        )
    ).mappings().one()
    assert len(row["reservation_id"]) <= 128
    assert row["action"] == "power:on"


def test_power_operation_store_round_trips_successful_operation(db_engine):
    store = PowerOperationStore(db_engine)
    operation = {
        "reservationId": "reservation-store-1",
        "labId": "lab-1",
        "phase": "pre_start",
        "controllerId": "mock-lab-01",
        "outlet": "1",
        "action": "on",
        "success": True,
        "status": "completed",
        "idempotencyKey": "reservation-store-1:lab-1:pre_start:policy-1:10:on",
        "observedStateBefore": "off",
        "observedStateAfter": "on",
        "durationMs": 4,
        "actor": "scheduler",
        "message": None,
    }

    store.save(operation)

    found = store.get_successful(operation["idempotencyKey"])
    assert found is not None
    assert found["success"] is True
    assert found["reservationId"] == "reservation-store-1"
    assert found["observedStateAfter"] == "on"
    assert store.list(reservation_id="reservation-store-1")[0]["action"] == "on"


def test_durable_idempotency_skips_operation_after_runtime_rebuild(db_engine):
    store = PowerOperationStore(db_engine)
    first_runtime = build_runtime(
        record_operation=worker._record_power_operation,
        operation_store=store,
    )

    first = first_runtime.execute_policy("lab-1", "reservation-durable-1", "pre_start", actor="scheduler")
    second_runtime = build_runtime(
        record_operation=worker._record_power_operation,
        operation_store=store,
    )
    second = second_runtime.execute_policy("lab-1", "reservation-durable-1", "pre_start", actor="scheduler")

    assert first["success"] is True
    assert [step["status"] for step in second["steps"]] == [
        "skipped_already_completed",
        "skipped_already_completed",
    ]
    assert second_runtime.operations("reservation-durable-1")[0]["reservationId"] == "reservation-durable-1"


def test_power_api_reads_durable_operation_history(client, db_engine, monkeypatch):
    store = PowerOperationStore(db_engine)
    runtime = build_runtime(
        record_operation=worker._record_power_operation,
        operation_store=store,
    )
    runtime.execute_policy("lab-1", "reservation-api-durable", "pre_start", actor="scheduler")
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    response = client.get("/api/power/operations?reservationId=reservation-api-durable")

    assert response.status_code == 200
    assert len(response.json["operations"]) == 2
    assert response.json["operations"][0]["reservationId"] == "reservation-api-durable"


def test_power_policy_update_is_validated_persisted_and_applied(tmp_path):
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(
        json.dumps(
            {
                "controllers": [
                    {
                        "id": "mock-lab-01",
                        "name": "Mock lab controller",
                        "driver": "mock",
                        "config": {"outlets": ["1"]},
                    }
                ],
                "outlets": [{"controllerId": "mock-lab-01", "outlet": "1"}],
                "policies": [
                    {
                        "id": "policy-1",
                        "labId": "lab-1",
                        "policyName": "Initial",
                        "steps": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    runtime = PowerRuntime.from_path(str(config_path))
    updated = runtime.update_policy(
        {
            "id": "policy-1",
            "labId": "lab-1",
            "policyName": "Updated",
            "enabled": True,
            "steps": [
                {
                    "phase": "start",
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "action": "on",
                },
                {
                    "phase": "end",
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "action": "off",
                },
                {
                    "phase": "start",
                    "controllerId": "mock-lab-01",
                    "outlet": "1",
                    "action": "on",
                },
            ],
        }
    )

    assert updated["policyName"] == "Updated"
    assert [step["phase"] for step in updated["steps"]] == ["start", "end", "start"]
    assert all("sequence" not in step for step in updated["steps"])
    assert runtime.describe_policies() == [updated]
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["policies"] == [updated]


def test_power_policy_update_rejects_invalid_policy_without_changing_file(tmp_path):
    config_path = tmp_path / "power-controllers.json"
    original = {
        "controllers": [],
        "outlets": [],
        "policies": [
            {"labId": "lab-1", "policyName": "Initial", "steps": []}
        ],
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    runtime = PowerRuntime.from_path(str(config_path))

    with pytest.raises(ValidationError, match="duplicate sequence"):
        runtime.update_policy(
            {
                "labId": "lab-1",
                "policyName": "Invalid",
                "steps": [
                    {
                        "phase": "pre_start",
                        "sequence": 10,
                        "controllerId": "controller",
                        "outlet": "1",
                        "action": "on",
                    },
                    {
                        "phase": "pre_start",
                        "sequence": 10,
                        "controllerId": "controller",
                        "outlet": "2",
                        "action": "off",
                    },
                ],
            }
        )

    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_power_policy_api_lists_and_updates_provider_policy(client, tmp_path, monkeypatch):
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(
        json.dumps({"controllers": [], "outlets": [], "policies": []}),
        encoding="utf-8",
    )
    runtime = PowerRuntime.from_path(str(config_path))
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    listed = client.get("/api/power/policies")
    assert listed.status_code == 200
    assert listed.json["policies"] == []

    updated = client.put(
        "/api/power/policies/lab-1",
        json={
            "policyName": "Provider policy",
            "steps": [],
        },
    )
    assert updated.status_code == 200
    assert updated.json["policy"]["labId"] == "lab-1"

    policy_with_ordered_steps = client.put(
        "/api/power/policies/lab-1",
        json={
            "policyName": "Provider ordered policy",
            "steps": [
                {
                    "phase": "start",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "on",
                },
                {
                    "phase": "end",
                    "controllerId": "controller",
                    "outlet": "1",
                    "action": "off",
                },
                {
                    "phase": "start",
                    "controllerId": "controller",
                    "outlet": "2",
                    "action": "on",
                },
            ],
        },
    )
    assert policy_with_ordered_steps.status_code == 200
    saved_steps = policy_with_ordered_steps.json["policy"]["steps"]
    assert [step["phase"] for step in saved_steps] == ["start", "end", "start"]
    assert all("sequence" not in step for step in saved_steps)

    mismatch = client.put(
        "/api/power/policies/lab-2",
        json={"labId": "lab-1", "policyName": "Mismatch", "steps": []},
    )
    assert mismatch.status_code == 400


def test_reservation_start_runs_pre_start_power_before_host_operations(db_engine, monkeypatch):
    events = []
    runtime = build_runtime(record_operation=lambda _operation: events.append("power"))
    monkeypatch.setattr(worker, "POWER_RUNTIME", runtime)
    worker.HOSTS = worker.HostRegistry({"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]})
    monkeypatch.setattr(
        worker,
        "perform_wake_step",
        lambda *args, **kwargs: (events.append("wake") or (True, {"action": "wake", "success": True})),
    )
    monkeypatch.setattr(
        worker,
        "perform_command_step",
        lambda *args, **kwargs: (
            events.append("prepare") or (True, {"action": "prepare", "success": True})
        ),
    )

    response, status = worker.handle_reservation_start(
        {"reservationId": "reservation-lifecycle-start", "host": "lab-ws-01", "labId": "lab-1"}
    )

    assert status == 200
    assert response["success"] is True
    assert events == ["power", "power", "wake", "prepare"]


def test_required_pre_start_power_failure_prevents_host_start(db_engine, monkeypatch):
    events = []
    runtime = build_runtime(record_operation=lambda _operation: events.append("power"))
    mock_driver(runtime).fail_action("on", outlet="1")
    monkeypatch.setattr(worker, "POWER_RUNTIME", runtime)
    worker.HOSTS = worker.HostRegistry({"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]})
    monkeypatch.setattr(worker, "perform_wake_step", lambda *args, **kwargs: events.append("wake"))
    monkeypatch.setattr(worker, "perform_command_step", lambda *args, **kwargs: events.append("prepare"))

    response, status = worker.handle_reservation_start(
        {"reservationId": "reservation-lifecycle-failure", "host": "lab-ws-01", "labId": "lab-1"}
    )

    assert status == 502
    assert response["success"] is False
    assert events == ["power"]


def test_reservation_end_runs_post_end_power_after_release(db_engine, monkeypatch):
    events = []
    runtime = build_runtime(record_operation=lambda _operation: events.append("power"))
    monkeypatch.setattr(worker, "POWER_RUNTIME", runtime)
    worker.HOSTS = worker.HostRegistry({"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]})
    monkeypatch.setattr(
        worker,
        "perform_command_step",
        lambda *args, **kwargs: (
            events.append("release") or (True, {"action": "release", "success": True})
        ),
    )

    response, status = worker.handle_reservation_end(
        {"reservationId": "reservation-lifecycle-end", "host": "lab-ws-01", "labId": "lab-1"}
    )

    assert status == 200
    assert response["success"] is True
    assert events == ["release", "power", "power"]


def test_policy_respects_local_mode_without_actuating_outlets():
    runtime = build_runtime()

    result = runtime.execute_policy(
        "lab-1",
        "reservation-local-mode",
        "pre_start",
        actor="scheduler",
        local_mode=True,
    )

    assert result["success"] is True
    assert result["status"] == "skipped_local_mode"
    assert mock_driver(runtime).states == {"1": "off", "2": "off"}


def test_end_failure_mode_warns_without_blocking_phase():
    runtime = build_runtime()
    mock_driver(runtime).fail_action("off", outlet="2")
    mock_driver(runtime).states["2"] = "on"

    result = runtime.execute_policy("lab-1", "reservation-end-warning", "post_end", actor="scheduler")

    assert result["success"] is True
    assert result["status"] == "completed_with_warnings"
    assert result["steps"][0]["success"] is False
