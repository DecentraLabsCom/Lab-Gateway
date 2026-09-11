from session_ticket_responses import extract_error_payload, extract_error_text


class _Response:
    def __init__(self, text, payload=None, error=None):
        self.text = text
        self._payload = payload
        self._error = error

    def json(self):
        if self._error is not None:
            raise self._error
        return self._payload


def test_extract_error_text_prefers_error_then_message():
    assert extract_error_text(_Response("fallback", {"error": "upstream error", "message": "message"})) == "upstream error"
    assert extract_error_text(_Response("fallback", {"message": "message"})) == "message"


def test_extract_error_text_falls_back_to_response_text_for_invalid_json():
    response = _Response("fallback", error=ValueError("invalid JSON"))

    assert extract_error_text(response) == "fallback"


def test_extract_error_payload_preserves_json_object():
    payload = {"code": "INVALID_TICKET", "error": "expired"}

    assert extract_error_payload(_Response("expired", payload)) == payload


def test_extract_error_payload_wraps_non_object_response():
    assert extract_error_payload(_Response("plain text", ["not", "an", "object"])) == {
        "error": "plain text",
    }
    assert extract_error_payload(_Response("invalid", error=ValueError("invalid JSON"))) == {
        "error": "invalid",
    }