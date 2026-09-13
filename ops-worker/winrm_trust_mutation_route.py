"""Composition for WinRM trust certificate mutation routes."""

import re
from typing import Any, Callable, Dict, Optional, Type

from werkzeug.datastructures import Headers


def _trust_error_code(error: BaseException) -> str:
    return str(getattr(error, "code", "WINRM_TRUST_INVALID"))


def handle_winrm_trust_put(
    host_name: str,
    *,
    headers: Headers,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    request_value: Callable[[str], str],
    normalize_trust_ref: Callable[[str], str],
    trust_ref_for_host: Callable[[Dict[str, Any]], str],
    read_certificate_upload: Callable[[], bytes],
    parse_certificate: Callable[[bytes], Any],
    validate_certificate: Callable[[Any, Dict[str, Any]], Dict[str, Any]],
    store_trust: Callable[[Dict[str, Any], Any], Dict[str, Any]],
    request_id: Callable[[], str],
    sanitize_log_value: Callable[[Any], str],
    log_info: Callable[..., Any],
    log_warning: Callable[..., Any],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    fingerprint_confirmation_required_message: str,
    fingerprint_mismatch_message: str,
    trust_ref_mismatch_message: str,
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Save a certificate after fingerprint and host trust confirmation."""
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404

    try:
        submitted_fingerprint = (
            request_value("fingerprintSha256")
            or str(headers.get("X-WinRM-Fingerprint-SHA256") or "").strip()
        )
        submitted_fingerprint = re.sub(r"[\s:]", "", submitted_fingerprint).upper()
        if not submitted_fingerprint:
            raise trust_error_type(
                "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED",
                fingerprint_confirmation_required_message,
            )
        if not re.fullmatch(r"[0-9A-F]{64}", submitted_fingerprint):
            raise trust_error_type("WINRM_FINGERPRINT_MISMATCH", fingerprint_mismatch_message)

        supplied_trust_ref = (
            request_value("trustRef")
            or str(headers.get("X-WinRM-Trust-Ref") or "").strip()
        )
        if supplied_trust_ref:
            try:
                if normalize_trust_ref(supplied_trust_ref) != trust_ref_for_host(host):
                    raise trust_error_type("WINRM_TRUST_REF_MISMATCH", trust_ref_mismatch_message)
            except ValueError as exc:
                raise trust_error_type("WINRM_TRUST_REF_MISMATCH", trust_ref_mismatch_message) from exc

        raw = read_certificate_upload()
        certificate = parse_certificate(raw)
        metadata = validate_certificate(certificate, host)
        if metadata["fingerprintSha256"] != submitted_fingerprint:
            raise trust_error_type("WINRM_FINGERPRINT_MISMATCH", fingerprint_mismatch_message)

        trust = store_trust(host, certificate)
        log_info(
            "WinRM trust saved host=%s fingerprintSha256=%s",
            sanitize_log_value(host_name),
            sanitize_log_value(metadata["fingerprintSha256"]),
        )
        return jsonify({
            "requestId": request_id(),
            "saved": True,
            "host": host.get("name"),
            "address": host.get("address"),
            "trust": trust,
        })
    except trust_error_type as exc:
        code = _trust_error_code(exc)
        return jsonify(trust_error_payload(host_name, code)), trust_http_status(code)
    except OSError as exc:
        log_warning(
            "Unable to save WinRM trust for %s: %s",
            sanitize_log_value(host_name),
            type(exc).__name__,
        )
        return jsonify(trust_error_payload(
            host_name,
            "WINRM_TRUST_STORAGE_UNAVAILABLE",
        )), 503
    except Exception as exc:
        return internal_error_response("WinRM trust save failed", exc)


def handle_winrm_trust_delete(
    host_name: str,
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    delete_trust: Callable[[Dict[str, Any]], None],
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    request_id: Callable[[], str],
    sanitize_log_value: Callable[[Any], str],
    log_info: Callable[..., Any],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Delete a host certificate and return its resulting inspected status."""
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        delete_trust(host)
        log_info("WinRM trust removed host=%s", sanitize_log_value(host_name))
        return jsonify({
            "requestId": request_id(),
            "deleted": True,
            "host": host.get("name"),
            "address": host.get("address"),
            "trust": inspect_trust(host),
        })
    except trust_error_type as exc:
        code = _trust_error_code(exc)
        return jsonify(trust_error_payload(host_name, code)), trust_http_status(code)
    except Exception as exc:
        return internal_error_response("WinRM trust delete failed", exc)


__all__ = ["handle_winrm_trust_delete", "handle_winrm_trust_put"]
