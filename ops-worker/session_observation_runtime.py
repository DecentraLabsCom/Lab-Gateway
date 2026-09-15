"""Composition adapter for the durable session-observation service."""

from collections.abc import Mapping
from typing import Any

from session_observation_context import SessionObservationContext


class SessionObservationRuntime:
    """Coordinate observation operations from explicit dependencies."""

    def __init__(self, context: SessionObservationContext):
        self._context = context

    def create_service(self) -> Any:
        context = self._context
        return context.get_session_observations_factory()(
            db_engine=context.get_db_engine(),
            guacamole_db_engine=context.get_guacamole_db_engine(),
            encrypt_secret=context.get_encrypt_secret(),
            decrypt_secret=context.get_decrypt_secret(),
            http_get=context.get_http_get(),
            http_post=context.get_http_post(),
            http_delete=context.get_http_delete(),
            sql_text=context.get_sql_text(),
            integrity_error_type=context.get_integrity_error_type(),
            enqueue_session_observation=lambda payload: context.get_enqueue_session_observation()(
                payload
            ),
            retry_delay=context.get_retry_delay(),
            to_utc=context.get_to_utc(),
            now=context.get_now(),
            current_epoch=context.get_current_epoch(),
            config=context.get_config(),
            logger=context.get_logger(),
        )

    def _service(self) -> Any:
        return self._context.get_service()

    def retry_delay_seconds(self, attempts: int) -> int:
        return self._context.get_retry_delay()(attempts)

    def encrypt_runtime_secret(self, value: str) -> str:
        return self._context.get_encrypt_secret()(value)

    def decrypt_runtime_secret(self, value: str) -> str:
        return self._context.get_decrypt_secret()(value)

    def enqueue_guacamole_token_revocation(self, payload: Mapping[str, Any]) -> bool:
        return self._service().enqueue_guacamole_token_revocation(payload)

    def guacamole_admin_session(self) -> Any:
        return self._service().guacamole_admin_session()

    def guacamole_connection_history_observed(self, row: Mapping[str, Any]) -> Any:
        return self._service().guacamole_connection_history_observed(row)

    def reconcile_guacamole_observations(self, admin_token: str, data_source: str) -> None:
        return self._service().reconcile_guacamole_observations(admin_token, data_source)

    def process_guacamole_token_revocations(self) -> int:
        return self._service().process_guacamole_token_revocations()

    def enqueue_session_observation(self, payload: Mapping[str, Any]) -> bool:
        return self._service().enqueue_session_observation(payload)

    def claim_session_observation_outbox_rows(self) -> Any:
        return self._service().claim_session_observation_outbox_rows()

    def mark_session_observation_delivered(self, record_id: int) -> None:
        return self._service().mark_session_observation_delivered(record_id)

    def mark_session_observation_failure(
        self,
        record: Mapping[str, Any],
        error: str,
    ) -> None:
        return self._service().mark_session_observation_failure(record, error)

    def session_observed_epoch(self, value: Any) -> int:
        return self._service().session_observed_epoch(value)

    def base64url_json(self, value: Mapping[str, Any]) -> str:
        return self._service().base64url_json(value)

    def session_observer_authorization(self) -> str:
        return self._service().session_observer_authorization()

    def deliver_session_observation_outbox(self) -> int:
        return self._service().deliver_session_observation_outbox()


def create_session_observation_runtime(
    context: SessionObservationContext,
) -> SessionObservationRuntime:
    """Create an observation runtime bound to explicit dependencies."""
    return SessionObservationRuntime(context)


__all__ = ["SessionObservationRuntime", "create_session_observation_runtime"]
