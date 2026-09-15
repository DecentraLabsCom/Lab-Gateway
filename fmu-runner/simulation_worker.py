"""Isolated FMU simulation worker executed by the process pool."""

try:
    import resource as posix_resource
except ImportError:
    posix_resource = None  # Not available on Windows

from typing import Any, Optional

from fmpy import simulate_fmu

from config import FMU_WORKER_ADDRESS_SPACE_LIMIT


def run_simulation(
    fmu_path: str,
    start_time: float,
    stop_time: float,
    step_size: float,
    start_values: dict,
    timeout: int,
    fmi_type: str = "CoSimulation",
    solver_name: str = "Euler",
    *,
    resource_api: Optional[Any] = posix_resource,
    address_space_limit: int = FMU_WORKER_ADDRESS_SPACE_LIMIT,
    simulate_fmu_fn: Any = simulate_fmu,
) -> dict:
    """Execute an FMU simulation and return JSON-compatible result data."""
    _apply_resource_limits(
        resource_api,
        timeout=timeout,
        address_space_limit=address_space_limit,
    )

    sim_kwargs: dict[str, Any] = {
        "start_time": start_time,
        "stop_time": stop_time,
        "step_size": step_size,
        "start_values": start_values,
        "fmi_type": fmi_type,
    }
    if fmi_type == "ModelExchange":
        sim_kwargs["solver"] = solver_name

    result = simulate_fmu_fn(fmu_path, **sim_kwargs)
    column_names = result.dtype.names
    if column_names is None:
        raise RuntimeError("FMU simulation returned no named result columns")

    outputs = {}
    time_values = []
    for name in column_names:
        values = result[name].tolist()
        if name.lower() == "time":
            time_values = values
        else:
            outputs[name] = values

    return {
        "time": time_values,
        "outputs": outputs,
        "outputVariables": list(outputs.keys()),
    }


def _apply_resource_limits(
    resource_api: Optional[Any],
    *,
    timeout: int,
    address_space_limit: int,
) -> None:
    """Apply best-effort Linux worker limits without breaking other hosts."""
    if resource_api is None:
        return
    try:
        resource_api.setrlimit(resource_api.RLIMIT_CPU, (timeout, timeout + 5))
        resource_api.setrlimit(
            resource_api.RLIMIT_AS,
            (address_space_limit, address_space_limit),
        )
    except Exception:
        # Resource limits may be unavailable or restricted on non-Linux hosts.
        return


__all__ = ["run_simulation"]
