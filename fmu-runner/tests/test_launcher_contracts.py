from pathlib import Path


def test_main_is_only_the_uvicorn_launcher():
    source = Path(__file__).parents[1].joinpath("main.py").read_text(encoding="utf-8")

    assert "from runner_application import app" in source
    assert "create_run_router" not in source
    assert "_runner_runtime" not in source
    assert "FastAPI" not in source
