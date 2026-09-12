from datetime import datetime, timezone

import worker


def test_rows_to_operations_contract_projects_public_names_and_coerces_success():
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    result = worker._rows_to_operations(
        [
            {
                "action": "prepare",
                "status": "completed",
                "success": 1,
                "message": "ready",
                "payload": '{"attempt": 1}',
                "response_code": 201,
                "duration_ms": 42,
                "created_at": created_at,
            }
        ]
    )

    assert result == [
        {
            "action": "prepare",
            "status": "completed",
            "success": True,
            "message": "ready",
            "payload": {"attempt": 1},
            "responseCode": 201,
            "durationMs": 42,
            "createdAt": created_at.isoformat(),
        }
    ]


def test_rows_to_operations_contract_preserves_non_json_payload_strings():
    result = worker._rows_to_operations(
        [
            {
                "action": "failure",
                "status": "completed",
                "success": 0,
                "message": None,
                "payload": "opaque payload",
                "response_code": None,
                "duration_ms": None,
                "created_at": None,
            }
        ]
    )

    assert result[0]["payload"] == "opaque payload"
    assert result[0]["success"] is False
    assert result[0]["createdAt"] is None


def test_rows_to_operations_contract_accepts_native_payloads_and_empty_rows():
    assert worker._rows_to_operations([]) == []
    result = worker._rows_to_operations(
        [
            {
                "action": "noop",
                "status": None,
                "success": None,
                "message": "",
                "payload": {"already": "decoded"},
                "response_code": 200,
                "duration_ms": 0,
                "created_at": "2026-01-02T03:04:05Z",
            }
        ]
    )

    assert result[0]["payload"] == {"already": "decoded"}
    assert result[0]["createdAt"] == "2026-01-02T03:04:05+00:00"
