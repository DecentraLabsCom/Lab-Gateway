"""Flask application hooks shared by the Ops Worker composition root."""

from collections.abc import Callable
import hmac
import logging
import re
from typing import Any, Mapping
from uuid import uuid4

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def requires_ops_internal_auth(path: str) -> bool:
    """Return whether *path* is an Ops API protected by the gateway token."""
    return path.startswith("/api/") or path.startswith("/aas-admin/")


def sanitize_log_value(value: Any) -> str:
    """Keep request-derived values on one physical log line."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def request_id_from_headers(
    headers: Mapping[str, Any],
    *,
    request_id_factory: Callable[[], str] = lambda: uuid4().hex,
    request_id_pattern: re.Pattern[str] = _REQUEST_ID_RE,
) -> str:
    """Return a bounded request correlation id from an HTTP header mapping."""
    candidate = str(headers.get("X-Request-ID") or "").strip()
    return candidate if request_id_pattern.fullmatch(candidate) else request_id_factory()


def internal_error_response(
    context: str,
    exc: BaseException,
    *,
    request_id: Callable[[], str],
    sanitize_log_value: Callable[[Any], str],
    log_exception: Callable[..., Any],
    jsonify: Callable[..., Any] = jsonify,
    success: Any = None,
    status: int = 500,
) -> Any:
    """Log details privately and return the stable public error payload."""
    del exc
    log_exception(
        "Ops Worker request failed context=%s",
        sanitize_log_value(context),
    )
    payload = {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": request_id(),
    }
    if success is not None:
        payload["success"] = success
    return jsonify(payload), status


def handle_unexpected_exception(
    exc: Exception,
    *,
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Keep Flask HTTP errors intact and map unexpected errors to the API contract."""
    if isinstance(exc, HTTPException):
        return exc
    return internal_error_response("Unhandled Ops Worker request", exc)


def check_ops_internal_auth(
    *,
    path: str,
    provided: str,
    token: str,
    requires_internal_auth: Callable[[str], bool],
    logger: Any = logging,
) -> Any:
    """Apply the gateway-local authentication contract to one request."""
    if not requires_internal_auth(path):
        return None

    if not token:
        logger.error("OPS_INTERNAL_AUTH_TOKEN is not configured; rejecting Ops API request")
        return jsonify({
            "success": False,
            "error": "Ops internal authentication is not configured",
        }), 503

    if not provided or not hmac.compare_digest(provided, token):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


def register_app_hooks(
    app: Flask,
    *,
    internal_error_response: Callable[[str, BaseException], Any],
    internal_auth_token: Callable[[], str],
    internal_auth_header: Callable[[], str],
    requires_internal_auth: Callable[[str], bool],
) -> None:
    """Register the process-wide error and internal-auth hooks on *app*."""

    @app.errorhandler(Exception)
    def _handle_unexpected_exception(exc: Exception):
        return handle_unexpected_exception(
            exc,
            internal_error_response=internal_error_response,
        )

    @app.before_request
    def _require_ops_internal_auth():
        header = str(internal_auth_header() or "")
        return check_ops_internal_auth(
            path=request.path,
            provided=request.headers.get(header, "") if header else "",
            token=str(internal_auth_token() or ""),
            requires_internal_auth=requires_internal_auth,
        )
