"""Composition adapter for Ops Worker application hooks."""

from typing import Any, Optional

from app_hooks_context import AppHooksContext


class AppHooksRuntime:
    """Expose security, request and error hooks through explicit dependencies."""

    def __init__(self, context: AppHooksContext):
        self._context = context

    def env_or_secret_file(self, name: str, default: str = "") -> str:
        context = self._context
        return context.get_env_or_secret_file_impl()(
            name,
            default,
            logger=context.get_logger(),
        )

    def sanitize_log_value(self, value: Any) -> str:
        return self._context.get_sanitize_log_value_impl()(value)

    def as_utc_datetime(self, value: Any) -> Optional[Any]:
        context = self._context
        return context.get_as_utc_datetime_impl()(
            value,
            parse_datetime=context.get_datetime().fromisoformat,
            utc_timezone=context.get_timezone().utc,
        )

    def parse_reservation_datetime(self, value: Any) -> Optional[Any]:
        return self.as_utc_datetime(value)

    def request_id(self) -> str:
        context = self._context
        return context.get_request_id_from_headers_impl()(
            context.get_request_headers()
        )

    def internal_error_response(
        self,
        context_name: str,
        exc: BaseException,
        *,
        success: Optional[bool] = None,
        status: int = 500,
    ) -> Any:
        context = self._context
        return context.get_internal_error_response_impl()(
            context_name,
            exc,
            request_id=context.get_request_id(),
            sanitize_log_value=context.get_sanitize_log_value(),
            log_exception=context.get_logger().exception,
            jsonify=context.get_jsonify(),
            success=success,
            status=status,
        )

    def handle_unexpected_exception(self, exc: Exception) -> Any:
        context = self._context
        return context.get_handle_unexpected_exception_impl()(
            exc,
            internal_error_response=context.get_internal_error_response(),
        )

    def requires_ops_internal_auth(self, path: str) -> bool:
        return self._context.get_requires_ops_internal_auth_impl()(path)

    def require_ops_internal_auth(self) -> Any:
        context = self._context
        headers = context.get_request_headers()
        header = context.get_ops_internal_auth_header()
        return context.get_check_ops_internal_auth_impl()(
            path=context.get_request_path(),
            provided=headers.get(header, ""),
            token=context.get_ops_internal_auth_token(),
            requires_internal_auth=context.get_requires_ops_internal_auth(),
        )


def create_app_hooks_runtime(context: AppHooksContext) -> AppHooksRuntime:
    """Create an application-hooks runtime bound to explicit providers."""
    return AppHooksRuntime(context)


__all__ = ["AppHooksRuntime", "create_app_hooks_runtime"]
