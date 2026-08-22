import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).with_name("simulate-proxy-fmu.py")


def _load_simulation_module():
    spec = importlib.util.spec_from_file_location("simulate_proxy_fmu", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_outputs_uses_value_reference_index():
    module = _load_simulation_module()
    output = SimpleNamespace(
        name="y",
        type="Float64",
        causality="output",
        valueReference=10,
        dimensions=[],
    )
    model_description = SimpleNamespace(modelVariables=[output])
    fmu = SimpleNamespace(getFloat64=lambda references: [1.25])

    assert module._read_outputs(fmu, model_description, [output]) == {"y": 1.25}
