"""Pure selection of the FMI execution type for simulation routes."""

from typing import Any, Callable


def resolve_fmi_type(
    requested_type: Any,
    fmu_path: str,
    model_description_reader: Callable[[str], Any],
) -> Any:
    """Honor an explicit type or detect it from the model description."""

    if requested_type:
        return requested_type

    try:
        model_description = model_description_reader(str(fmu_path))
        return (
            "CoSimulation"
            if model_description.coSimulation
            else ("ModelExchange" if model_description.modelExchange else "CoSimulation")
        )
    except Exception:
        return "CoSimulation"
