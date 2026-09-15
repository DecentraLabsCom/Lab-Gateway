import numpy as np
import pytest

from simulation_worker import run_simulation


def _result_array():
    return np.array(
        [(0.0, 1.0), (0.5, 2.0)],
        dtype=[("time", float), ("output", float)],
    )


class _ResourceApi:
    RLIMIT_CPU = "cpu"
    RLIMIT_AS = "address-space"

    def __init__(self):
        self.calls = []

    def setrlimit(self, resource, limits):
        self.calls.append((resource, limits))


def test_run_simulation_applies_limits_and_normalizes_fmpy_result():
    resource_api = _ResourceApi()
    calls = []

    def simulate(path, **kwargs):
        calls.append((path, kwargs))
        return _result_array()

    result = run_simulation(
        "/tmp/model.fmu",
        0.0,
        1.0,
        0.5,
        {"u": 3.0},
        12,
        resource_api=resource_api,
        address_space_limit=2048,
        simulate_fmu_fn=simulate,
    )

    assert resource_api.calls == [
        ("cpu", (12, 17)),
        ("address-space", (2048, 2048)),
    ]
    assert calls == [
        (
            "/tmp/model.fmu",
            {
                "start_time": 0.0,
                "stop_time": 1.0,
                "step_size": 0.5,
                "start_values": {"u": 3.0},
                "fmi_type": "CoSimulation",
            },
        )
    ]
    assert result == {
        "time": [0.0, 0.5],
        "outputs": {"output": [1.0, 2.0]},
        "outputVariables": ["output"],
    }


def test_run_simulation_adds_solver_only_for_model_exchange():
    calls = []

    def simulate(_path, **kwargs):
        calls.append(kwargs)
        return _result_array()

    run_simulation(
        "model.fmu",
        0.0,
        1.0,
        0.1,
        {},
        10,
        resource_api=None,
        simulate_fmu_fn=simulate,
        fmi_type="ModelExchange",
        solver_name="CVode",
    )

    assert calls[0]["solver"] == "CVode"


def test_run_simulation_rejects_results_without_named_columns():
    class _UnnamedResult:
        dtype = type("DType", (), {"names": None})()

    with pytest.raises(RuntimeError, match="no named result columns"):
        run_simulation(
            "model.fmu",
            0.0,
            1.0,
            0.1,
            {},
            10,
            resource_api=None,
            simulate_fmu_fn=lambda *_args, **_kwargs: _UnnamedResult(),
        )
