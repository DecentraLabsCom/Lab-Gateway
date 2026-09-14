"""Composition adapter for the durable session-observation service."""

from collections.abc import Mapping
from typing import Any


class SessionObservationRuntime:
    """Build observation services from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def create_service(self) -> Any:
        get = self._get
        return get("SessionObservations")(
            db_engine=get("DB_ENGINE"),
            guacamole_db_engine=get("GUACAMOLE_DB_ENGINE"),
            encrypt_secret=lambda value: get("_encrypt_runtime_secret")(value),
            decrypt_secret=lambda value: get("_decrypt_runtime_secret")(value),
            http_get=get("requests").get,
            http_post=get("requests").post,
            http_delete=get("requests").delete,
            sql_text=get("text"),
            integrity_error_type=get("IntegrityError"),
            enqueue_session_observation=lambda payload: get("enqueue_session_observation")(
                payload
            ),
            retry_delay=get("session_observation_retry_delay_seconds"),
            to_utc=get("to_utc"),
            now=lambda: get("datetime").now(get("timezone").utc),
            current_epoch=get("time").time,
            config={
                "access_audit_url": get("ACCESS_AUDIT_URL"),
                "session_observer_gateway_id": get("SESSION_OBSERVER_GATEWAY_ID"),
                "session_observer_signing_secret": get("SESSION_OBSERVER_SIGNING_SECRET"),
                "session_observation_outbox_enabled": get(
                    "SESSION_OBSERVATION_OUTBOX_ENABLED"
                ),
                "session_observation_outbox_batch_size": get(
                    "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE"
                ),
                "session_observation_outbox_max_attempts": get(
                    "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS"
                ),
                "session_observation_outbox_request_timeout_seconds": get(
                    "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS"
                ),
                "guac_admin_user": get("GUAC_ADMIN_USER"),
                "guac_admin_pass": get("GUAC_ADMIN_PASS"),
                "guac_api_url": get("GUAC_API_URL"),
                "guac_token_revocation_max_attempts": get(
                    "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS"
                ),
                "guacamole_history_lookback_seconds": get(
                    "GUACAMOLE_HISTORY_LOOKBACK_SECONDS"
                ),
                "guacamole_history_reconciliation_retention_seconds": get(
                    "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS"
                ),
            },
            logger=get("logging"),
        )

    def _service(self) -> Any:
        return self._get("_session_observations_service")()

    def retry_delay_seconds(self, attempts: int) -> int:
        return self._get("_default_retry_delay_seconds_impl")(attempts)

    def encrypt_runtime_secret(self, value: str) -> str:
        return self._get("_encrypt_secret_impl")(
            value,
            load_fernet=self._get("_load_fernet"),
        )

    def decrypt_runtime_secret(self, value: str) -> str:
        return self._get("_decrypt_secret_impl")(
            value,
            load_fernet=self._get("_load_fernet"),
        )

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
    providers: Mapping[str, Any],
) -> SessionObservationRuntime:
    """Create a runtime adapter bound to live worker providers."""
    return SessionObservationRuntime(providers)


__all__ = ["SessionObservationRuntime", "create_session_observation_runtime"]
