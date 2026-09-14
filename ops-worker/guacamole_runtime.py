"""Composition adapter for Guacamole catalog and temporary-user operations."""

from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple


class GuacamoleRuntime:
    """Resolve Guacamole operations from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def load_guacamole_connections(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        get = self._get
        return get("_load_guacamole_connections_impl")(
            get("GUACAMOLE_DB_ENGINE"),
            sql_text=get("text"),
            logger=get("logging"),
        )

    def require_guacamole_provisioner_auth(self) -> Any:
        get = self._get
        return get("_check_guacamole_provisioner_auth_impl")(
            get("request").headers,
            expected_token=get("GUACAMOLE_PROVISIONER_TOKEN"),
            token_header=get("GUACAMOLE_PROVISIONER_TOKEN_HEADER"),
            jsonify=get("jsonify"),
        )

    def parse_guacamole_selector(self, selector: Any) -> int:
        return self._get("_parse_guacamole_selector_impl")(
            selector,
            selector_pattern=self._get("GUAC_SELECTOR_RE"),
        )

    def safe_connection_response(self, connection: Dict[str, Any]) -> Dict[str, Any]:
        return self._get("_safe_connection_response_impl")(connection)

    def provision_guacamole_temporary_user(
        self,
        selector: str,
        session_id: str,
        valid_until_epoch: Optional[Any],
        activate: bool = True,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_provision_guacamole_user_impl")(
            selector,
            session_id,
            valid_until_epoch,
            activate,
            engine=get("GUACAMOLE_DB_ENGINE"),
            parse_selector=get("parse_guacamole_selector"),
            resolve_connection=get("resolve_guacamole_connection"),
            safe_connection_response=get("safe_connection_response"),
            sql_text=get("text"),
            date_from_epoch=lambda epoch: get("datetime").fromtimestamp(
                epoch,
                tz=get("timezone").utc,
            ).date().isoformat(),
            logger=get("logging"),
        )

    def delete_guacamole_temporary_user(self, session_id: str) -> bool:
        get = self._get
        return get("_delete_guacamole_user_impl")(
            session_id,
            engine=get("GUACAMOLE_DB_ENGINE"),
            sql_text=get("text"),
            logger=get("logging"),
        )

    def cleanup_expired_guacamole_temp_users(self) -> int:
        get = self._get
        return get("_cleanup_guacamole_users_impl")(
            engine=get("GUACAMOLE_DB_ENGINE"),
            sql_text=get("text"),
            logger=get("logging"),
        )


def create_guacamole_runtime(providers: Mapping[str, Any]) -> GuacamoleRuntime:
    """Create a Guacamole adapter bound to live providers."""
    return GuacamoleRuntime(providers)


__all__ = ["GuacamoleRuntime", "create_guacamole_runtime"]
