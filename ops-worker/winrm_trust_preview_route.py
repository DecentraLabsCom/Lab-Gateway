"""Composition for the WinRM trust certificate preview HTTP route."""

from typing import Any, Callable, Dict, Optional, Type


def handle_winrm_trust_preview(
    host_name: str,
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    read_certificate_upload: Callable[[], bytes],
    parse_certificate: Callable[[bytes], Any],
    response_metadata: Callable[[Any, Dict[str, Any], str], Dict[str, Any]],
    validate_certificate: Callable[[Any, Dict[str, Any]], Any],
    request_id: Callable[[], str],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Preview a certificate without persisting it or exposing parser details."""
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404

    try:
        raw = read_certificate_upload()
        certificate = parse_certificate(raw)
        input_format = "PEM" if b"-----BEGIN CERTIFICATE-----" in raw[:256] else "DER"
        preview = response_metadata(certificate, host, input_format)
        try:
            validate_certificate(certificate, host)
        except trust_error_type as exc:
            code = getattr(exc, "code", "WINRM_TRUST_INVALID")
            payload = trust_error_payload(host_name, code)
            payload["preview"] = preview
            return jsonify(payload), trust_http_status(code)
        preview["valid"] = True
        return jsonify({
            "requestId": request_id(),
            "host": host.get("name"),
            "address": host.get("address"),
            "preview": preview,
        })
    except trust_error_type as exc:
        code = getattr(exc, "code", "WINRM_TRUST_INVALID")
        return jsonify(trust_error_payload(host_name, code)), trust_http_status(code)
    except Exception as exc:
        return internal_error_response("WinRM trust preview failed", exc)


__all__ = ["handle_winrm_trust_preview"]
