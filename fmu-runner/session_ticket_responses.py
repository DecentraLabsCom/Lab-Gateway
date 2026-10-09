from typing import Any


def extract_error_text(response: Any) -> str:
    detail_text = response.text
    try:
        detail_json = response.json()
    except (ValueError, TypeError):
        detail_json = None
    if isinstance(detail_json, dict):
        detail_text = detail_json.get("error") or detail_json.get("message") or detail_text
    return detail_text


def extract_error_payload(response: Any) -> dict[str, Any]:
    detail = {"error": response.text}
    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        detail = payload
    return detail
