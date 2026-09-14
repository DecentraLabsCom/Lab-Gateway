import worker
from runtime_context import RuntimeContext


def test_runtime_context_keeps_a_live_read_only_view_of_worker_values():
    values = {"token": "initial"}
    context = RuntimeContext(values)

    assert context["token"] == "initial"
    values["token"] = "rotated"
    assert context["token"] == "rotated"
    assert list(context) == ["token"]
    assert len(context) == 1


def test_worker_uses_the_explicit_runtime_context_for_blueprints_and_facades():
    assert isinstance(worker._RUNTIME_CONTEXT, RuntimeContext)
    assert worker._RUNTIME_CONTEXT["APP"] is worker.APP
