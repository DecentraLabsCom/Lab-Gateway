from pathlib import Path

import pytest


RUNNER_APPLICATION = Path(__file__).parents[1] / "runner_application.py"


@pytest.mark.parametrize(
    "alias",
    [
        "fmu_realtime_sessions",
        "fmu_realtime_sessions_internal",
        "download_proxy_fmu",
        "run_simulation",
        "cancel_simulation",
        "stream_simulation",
    ],
)
def test_runner_application_does_not_export_legacy_endpoint_aliases(alias):
    source = RUNNER_APPLICATION.read_text(encoding="utf-8")

    assert f"{alias} =" not in source
    assert f"Keep the historical private symbol" not in source
