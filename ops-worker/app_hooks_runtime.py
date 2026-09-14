"""Composition adapter for the Ops Worker application hooks."""

from collections.abc import Mapping
from typing import Any, Optional


class AppHooksRuntime:
    """Resolve process-wide hook helpers from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def env_or_secret_file(self, name: str, default: str = "") -> str:
        get = self._get
        return get("_env_or_secret_file_impl")(
            name,
            default,
            logger=get("logging"),
        )

    def sanitize_log_value(self, value: Any) -> str:
        return self._get("_sanitize_log_value_impl")(value)

    def as_utc_datetime(self, value: Any) -> Optional[Any]:
        get = self._get
        return get("_as_utc_datetime_impl")(
            value,
            parse_datetime=get("datetime").fromisoformat,
            utc_timezone=get("timezone").utc,
        )

    def parse_reservation_datetime(self, value: Any) -> Optional[Any]:
        return self.as_utc_datetime(value)

    def request_id(self) -> str:
        request = self._get("request")
        return self._get("_request_id_from_headers_impl")(request.headers)

    def internal_error_response(
        self,
        context: str,
        exc: BaseException,
        *,
        success: Optional[bool] = None,
        status: int = 500,
    ) -> Any:
        get = self._get
        return get("_internal_error_response_impl")(
            context,
            exc,
            request_id=get("_request_id"),
            sanitize_log_value=get("_sanitize_log_value"),
            log_exception=get("logging").exception,
            jsonify=get("jsonify"),
            success=success,
            status=status,
        )

    def handle_unexpected_exception(self, exc: Exception) -> Any:
        return self._get("_handle_unexpected_exception_impl")(
            exc,
            internal_error_response=self._get("internal_error_response"),
        )

    def requires_ops_internal_auth(self, path: str) -> bool:
        return self._get("_requires_ops_internal_auth_impl")(path)

    def require_ops_internal_auth(self) -> Any:
        get = self._get
        request = get("request")
        return get("_check_ops_internal_auth_impl")(
            path=request.path,
            provided=request.headers.get(get("OPS_INTERNAL_AUTH_HEADER"), ""),
            token=get("OPS_INTERNAL_AUTH_TOKEN"),
            requires_internal_auth=get("_requires_ops_internal_auth"),
        )


def create_app_hooks_runtime(providers: Mapping[str, Any]) -> AppHooksRuntime:
    """Create an application-hooks adapter bound to live providers."""
    return AppHooksRuntime(providers)


__all__ = ["AppHooksRuntime", "create_app_hooks_runtime"]
