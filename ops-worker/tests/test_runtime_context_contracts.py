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


def test_worker_builds_blueprints_from_an_explicit_runtime_context():
    context = worker._worker_runtime_context(worker.__dict__)

    assert isinstance(context, RuntimeContext)
    assert context["APP"] is worker.APP
    assert context["hmac"] is worker.hmac
