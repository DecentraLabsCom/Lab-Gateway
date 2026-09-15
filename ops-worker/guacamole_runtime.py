"""Composition adapter for Guacamole catalog and temporary-user operations."""

from typing import Any, Dict, List, Optional, Tuple

from guacamole_context import GuacamoleContext


class GuacamoleRuntime:
    """Expose Guacamole operations through explicit dependencies."""

    def __init__(self, context: GuacamoleContext):
        self._context = context

    def load_guacamole_connections(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        context = self._context
        return context.get_load_connections_impl()(
            context.get_db_engine(),
            sql_text=context.get_sql_text(),
            logger=context.get_logger(),
        )

    def require_guacamole_provisioner_auth(self) -> Any:
        context = self._context
        return context.get_check_auth_impl()(
            context.get_request_headers(),
            expected_token=context.get_expected_token(),
            token_header=context.get_token_header(),
            jsonify=context.get_jsonify(),
        )

    def parse_guacamole_selector(self, selector: Any) -> int:
        context = self._context
        return context.get_parse_selector_impl()(
            selector,
            selector_pattern=context.get_selector_pattern(),
        )

    def safe_connection_response(self, connection: Dict[str, Any]) -> Dict[str, Any]:
        return self._context.get_safe_connection_response_impl()(connection)

    def provision_guacamole_temporary_user(
        self,
        selector: str,
        session_id: str,
        valid_until_epoch: Optional[Any],
        activate: bool = True,
    ) -> Dict[str, Any]:
        context = self._context
        return context.get_provision_impl()(
            selector,
            session_id,
            valid_until_epoch,
            activate,
            engine=context.get_db_engine(),
            parse_selector=context.get_parse_selector(),
            resolve_connection=context.get_resolve_connection(),
            safe_connection_response=context.get_safe_connection_response(),
            sql_text=context.get_sql_text(),
            date_from_epoch=lambda epoch: context.get_datetime().fromtimestamp(
                epoch,
                tz=context.get_timezone().utc,
            ).date().isoformat(),
            logger=context.get_logger(),
        )

    def delete_guacamole_temporary_user(self, session_id: str) -> bool:
        context = self._context
        return context.get_delete_impl()(
            session_id,
            engine=context.get_db_engine(),
            sql_text=context.get_sql_text(),
            logger=context.get_logger(),
        )

    def cleanup_expired_guacamole_temp_users(self) -> int:
        context = self._context
        return context.get_cleanup_impl()(
            engine=context.get_db_engine(),
            sql_text=context.get_sql_text(),
            logger=context.get_logger(),
        )


def create_guacamole_runtime(context: GuacamoleContext) -> GuacamoleRuntime:
    """Create a Guacamole runtime bound to explicit dependencies."""
    return GuacamoleRuntime(context)


__all__ = ["GuacamoleRuntime", "create_guacamole_runtime"]
