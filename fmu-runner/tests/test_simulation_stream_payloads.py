from simulation_stream_payloads import (
    build_completed_event,
    iter_result_chunks,
)


def test_iter_result_chunks_keeps_empty_result_without_data_events():
    assert list(iter_result_chunks({"time": [], "outputs": {}})) == []


def test_iter_result_chunks_keeps_one_sample_chunks_for_short_results():
    result = {
        "time": [0.0, 0.1, 0.2],
        "outputs": {"position": [1.0, 1.1, 1.2]},
    }

    assert list(iter_result_chunks(result)) == [
        {
            "type": "data",
            "chunkIndex": 0,
            "totalChunks": 3,
            "time": [0.0],
            "outputs": {"position": [1.0]},
        },
        {
            "type": "data",
            "chunkIndex": 1,
            "totalChunks": 3,
            "time": [0.1],
            "outputs": {"position": [1.1]},
        },
        {
            "type": "data",
            "chunkIndex": 2,
            "totalChunks": 3,
            "time": [0.2],
            "outputs": {"position": [1.2]},
        },
    ]


def test_iter_result_chunks_slices_time_and_outputs_into_ten_or_more_chunks():
    result = {
        "time": list(range(25)),
        "outputs": {"position": list(range(100, 125))},
    }

    chunks = list(iter_result_chunks(result))

    assert len(chunks) == 13
    assert chunks[0] == {
        "type": "data",
        "chunkIndex": 0,
        "totalChunks": 13,
        "time": [0, 1],
        "outputs": {"position": [100, 101]},
    }
    assert chunks[-1]["chunkIndex"] == 12
    assert chunks[-1]["time"] == [24]
    assert chunks[-1]["outputs"] == {"position": [124]}


def test_build_completed_event_preserves_stream_contract_and_defaults():
    assert build_completed_event(
        sim_id="sim-1",
        simulation_time=0.123,
        fmi_type="CoSimulation",
        simulation_result={},
    ) == {
        "type": "completed",
        "simId": "sim-1",
        "simulationTime": 0.123,
        "fmiType": "CoSimulation",
        "outputVariables": [],
    }
