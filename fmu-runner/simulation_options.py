"""Pure parsing and validation for FMU simulation execution options."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping


class SimulationOptionsError(ValueError):
    """A user supplied simulation option violates the public request contract."""


@dataclass(frozen=True)
class SimulationOptions:
    start_time: float
    stop_time: float
    step_size: float
    timeout: int
    fmi_type: Any
    solver_name: Any


def parse_simulation_options(
    options: Mapping[str, Any],
    *,
    max_timeout: int,
    max_stop_time: float,
    min_step_size: float,
    effective_timeout_seconds: Callable[[int], int],
) -> SimulationOptions:
    """Parse and validate options while preserving the route's error order."""

    start_time = float(options.get("startTime", 0))
    stop_time = float(options.get("stopTime", 10))
    step_size = float(options.get("stepSize", 0.01))
    requested_timeout = int(options.get("timeout", max_timeout))

    if stop_time <= start_time:
        raise SimulationOptionsError("stopTime must be greater than startTime")
    if step_size <= 0:
        raise SimulationOptionsError("stepSize must be positive")
    if requested_timeout <= 0:
        raise SimulationOptionsError("timeout must be positive")

    timeout = effective_timeout_seconds(requested_timeout)

    if stop_time > max_stop_time:
        raise SimulationOptionsError(f"stopTime exceeds maximum ({max_stop_time}s)")
    if step_size < min_step_size:
        raise SimulationOptionsError(f"stepSize below minimum ({min_step_size}s)")

    return SimulationOptions(
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        timeout=timeout,
        fmi_type=options.get("fmiType", None),
        solver_name=options.get("solver", "Euler"),
    )
