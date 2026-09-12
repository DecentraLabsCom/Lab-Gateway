"""HTTP discovery helpers for Lab Station hosts."""

import json
from collections.abc import Callable, Sequence
from typing import Any, Dict, Optional, Tuple, Type


def response_looks_like_labstation(response: Any) -> Tuple[bool, Optional[str]]:
    service = None
    try:
        body = response.json()
        if isinstance(body, dict):
            service = body.get("service") or body.get("name") or body.get("app")
            text_blob = json.dumps(body).lower()
        else:
            text_blob = str(body).lower()
    except ValueError:
        text_blob = response.text.lower()

    detected = "labstation" in text_blob or str(service or "").lower() == "labstation"
    return detected, service


def probe_labstation_http(
    host: str,
    *,
    ports: Sequence[int],
    paths: Sequence[str],
    timeout: float,
    http_get: Callable[..., Any],
    request_exception_type: Type[BaseException],
    response_classifier: Callable[[Any], Tuple[bool, Optional[str]]],
    suggest_mac: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    if not host:
        return {"checked": False, "detected": False, "status": "missing-hostname"}

    for port in ports:
        for path in paths:
            url = f"http://{host}:{port}{path}"
            try:
                response = http_get(url, timeout=timeout)
            except request_exception_type:
                continue
            detected, service = response_classifier(response)
            if detected:
                result = {
                    "checked": True,
                    "detected": True,
                    "url": url,
                    "statusCode": response.status_code,
                    "service": service,
                }
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        mac_hint = suggest_mac(body)
                        if mac_hint:
                            result["suggestedMac"] = mac_hint
                except ValueError:
                    # A malformed response body simply has no MAC hint.
                    pass
                return result

    return {"checked": True, "detected": False, "status": "no-response"}
