from fastapi import HTTPException

from stream_errors import build_stream_error_payload


def test_build_stream_error_payload_preserves_valid_public_error_fields():
    assert build_stream_error_payload(
        HTTPException(
            status_code=503,
            detail={"code": "SESSION_FAILED", "error": "not persisted"},
        ),
        sim_id="sim-1",
    ) == {
        "type": "error",
        "simId": "sim-1",
        "code": "SESSION_FAILED",
        "detail": "not persisted",
    }


def test_build_stream_error_payload_uses_safe_defaults_for_untrusted_details():
    assert build_stream_error_payload(
        HTTPException(
            status_code=500,
            detail={"code": "bad-code", "error": "x" * 257},
        )
    ) == {
        "type": "error",
        "detail": "Simulation failed",
    }


def test_build_stream_error_payload_does_not_expose_non_http_exceptions():
    assert build_stream_error_payload(RuntimeError("secret upstream detail"), sim_id="sim-2") == {
        "type": "error",
        "simId": "sim-2",
        "detail": "Simulation failed",
    }