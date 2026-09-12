"""Pure payload builders for the FMU simulation NDJSON stream."""

from typing import Any, Iterator, Mapping


def iter_result_chunks(simulation_result: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield result chunks using the stream endpoint's existing sizing rules."""

    time_data = simulation_result.get("time", [])
    chunk_size = max(1, len(time_data) // 10)
    total_chunks = max(1, -(-len(time_data) // chunk_size))
    outputs = simulation_result.get("outputs", {})

    for idx in range(0, len(time_data), chunk_size):
        yield {
            "type": "data",
            "chunkIndex": idx // chunk_size,
            "totalChunks": total_chunks,
            "time": time_data[idx:idx + chunk_size],
            "outputs": {
                key: values[idx:idx + chunk_size]
                for key, values in outputs.items()
            },
        }


def build_completed_event(
    *,
    sim_id: str,
    simulation_time: float,
    fmi_type: Any,
    simulation_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the final event emitted after all simulation result chunks."""

    return {
        "type": "completed",
        "simId": sim_id,
        "simulationTime": simulation_time,
        "fmiType": fmi_type,
        "outputVariables": simulation_result.get("outputVariables", []),
    }
