"""Application construction for the Ops Worker Flask service."""

from collections.abc import Callable, Mapping
from typing import Any

from flask import Flask

from app_hooks import register_app_hooks
from aas_lab_sync_blueprint import create_aas_lab_sync_blueprint
from aas_sync_blueprint import create_aas_sync_blueprint
from guacamole_connections_blueprint import create_guacamole_connections_blueprint
from guacamole_provision_blueprint import create_guacamole_provision_blueprint
from health_blueprint import create_health_blueprint
from heartbeat_poll_blueprint import create_heartbeat_poll_blueprint
from heartbeat_stream_blueprint import create_heartbeat_stream_blueprint
from host_provision_blueprint import create_host_provision_blueprint
from host_update_blueprint import create_host_update_blueprint
from hosts_blueprint import create_hosts_blueprint
from hosts_discover_blueprint import create_hosts_discover_blueprint
from hosts_reload_blueprint import create_hosts_reload_blueprint
from internal_ingest_blueprint import create_internal_ingest_blueprint
from lab_associations_blueprint import create_lab_associations_blueprint
from lifecycle_blueprint import create_lifecycle_blueprint
from local_mode_blueprint import create_local_mode_blueprint
from operations_blueprint import create_operations_blueprint
from physical_operations_blueprint import create_physical_operations_blueprint
from timeline_blueprint import create_timeline_blueprint
from winrm_credentials_blueprint import create_winrm_credentials_blueprint
from winrm_trust_blueprint import create_winrm_trust_blueprint
from winrm_trust_mutation_blueprint import create_winrm_trust_mutation_blueprint
from winrm_trust_preview_blueprint import create_winrm_trust_preview_blueprint


def create_app(
    import_name: str,
    *,
    internal_error_response: Callable[[str, BaseException], Any],
    internal_auth_token: Callable[[], str],
    internal_auth_header: Callable[[], str],
    requires_internal_auth: Callable[[str], bool],
) -> Flask:
    """Create a Flask app and install its cross-cutting request hooks."""
    app = Flask(import_name)
    register_app_hooks(
        app,
        internal_error_response=internal_error_response,
        internal_auth_token=internal_auth_token,
        internal_auth_header=internal_auth_header,
        requires_internal_auth=requires_internal_auth,
    )
    return app


def register_blueprints(app: Flask, providers: Mapping[str, Any]) -> None:
    """Register every Ops Worker capability from a live provider namespace.

    ``worker`` passes its module globals as *providers*.  Lambdas resolve
    mutable providers at request time so existing monkeypatch points and the
    runtime reload behavior remain intact while registration lives here.
    """
    get = providers.__getitem__

    app.register_blueprint(get("power_bp"))
    app.register_blueprint(
        create_health_blueprint(
            get_db_engine=lambda: get("DB_ENGINE"),
            get_guacamole_db_engine=lambda: get("GUACAMOLE_DB_ENGINE"),
            database_is_usable=lambda engine, statement: get("database_is_usable")(
                engine,
                statement,
            ),
            fernet_key_is_usable=lambda: get("fernet_key_is_usable")(),
            demo_readiness=lambda: get("demo_readiness")(),
            get_hosts_loaded=lambda: len(get("HOSTS").all_hosts()),
            build_health_response=lambda **kwargs: get("_build_health_response_impl")(**kwargs),
            sql_text=lambda statement: get("text")(statement),
            log_warning=lambda message, value: get("logging").warning(message, value),
        )
    )
    app.register_blueprint(
        create_physical_operations_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            is_valid_ping_target=lambda value: get("_is_valid_ping_target")(value),
            wol_and_wait=lambda *args, **kwargs: get("wol_and_wait")(*args, **kwargs),
            now=lambda: get("time").time(),
            allowed_commands=get("ALLOWED_WINRM_COMMANDS"),
            run_command=lambda **kwargs: get("run_labstation_command")(**kwargs),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=lambda host_name, code: get("_winrm_trust_error_payload")(
                host_name,
                code,
            ),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_heartbeat_poll_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            poll_heartbeat=lambda host, include_events: get("poll_heartbeat")(
                host,
                include_events=include_events,
            ),
            now=lambda: get("time").time(),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=lambda host_name, code: get("_winrm_trust_error_payload")(
                host_name,
                code,
            ),
            request_id=lambda: get("_request_id")(),
            missing_credentials_predicate=lambda error: get(
                "is_missing_winrm_credentials_error"
            )(error),
            credentials_required_message=lambda: get("WINRM_CREDENTIALS_REQUIRED_MESSAGE"),
            internal_error_response=lambda message, exc: get("internal_error_response")(
                message,
                exc,
            ),
        )
    )
    app.register_blueprint(
        create_heartbeat_stream_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            generate_stream=lambda host, include_events: get("generate_heartbeat_stream")(
                host,
                include_events,
            ),
            response_factory=lambda *args, **kwargs: get("Response")(*args, **kwargs),
            stream_with_context=lambda *args, **kwargs: get("stream_with_context")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_lifecycle_blueprint(
            reservation_start=lambda payload: get("handle_reservation_start")(payload),
            reservation_end=lambda payload: get("handle_reservation_end")(payload),
            demo_start=lambda payload: get("handle_demo_start")(payload),
            demo_event=lambda payload: get("handle_demo_event")(payload),
            demo_end=lambda payload: get("handle_demo_end")(payload),
        )
    )
    app.register_blueprint(
        create_timeline_blueprint(
            get_db_engine=lambda: get("DB_ENGINE"),
            sanitize_limit=lambda value: get("_sanitize_limit")(value),
            sanitize_offset=lambda value: get("_sanitize_offset")(value),
            build_timeline=lambda reservation_id, limit, offset: get(
                "build_reservation_timeline"
            )(reservation_id, limit, offset),
            internal_error_response=lambda message, exc: get("internal_error_response")(
                message,
                exc,
            ),
        )
    )
    app.register_blueprint(
        create_hosts_blueprint(
            build_inventory=lambda: get("build_host_inventory")(),
        )
    )
    app.register_blueprint(
        create_lab_associations_blueprint(
            resolve_lab_associations=lambda: get("resolve_lab_associations")(),
        )
    )
    app.register_blueprint(
        create_guacamole_connections_blueprint(
            authorize=lambda: get("require_guacamole_provisioner_auth")(),
            load_connections=lambda: get("load_guacamole_connections")(),
            safe_connection_response=lambda connection: get("safe_connection_response")(
                connection
            ),
        )
    )
    app.register_blueprint(
        create_guacamole_provision_blueprint(
            authorize=lambda: get("require_guacamole_provisioner_auth")(),
            provision_temporary_user=lambda selector, session_id, valid_until, activate: get(
                "provision_guacamole_temporary_user"
            )(selector, session_id, valid_until, activate),
            delete_temporary_user=lambda session_id: get("delete_guacamole_temporary_user")(
                session_id
            ),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_hosts_discover_blueprint(
            resolve_connection=lambda connection_id: get("resolve_guacamole_connection")(
                connection_id
            ),
            discover_candidate=lambda connection: get("discover_labstation_candidate")(connection),
        )
    )
    app.register_blueprint(
        create_host_provision_blueprint(
            resolve_connection=lambda connection_id: get("resolve_guacamole_connection")(
                connection_id
            ),
            discover_candidate=lambda connection: get("discover_labstation_candidate")(connection),
            enough_discovery_signals=get("ENOUGH_DISCOVERY_SIGNALS"),
            build_host=lambda payload, connection: get("build_provisioned_host")(
                payload,
                connection,
            ),
            find_host=lambda host_name: get("HOSTS").get(host_name),
            upsert_host=lambda host: get("upsert_dynamic_host")(host),
            reload_hosts=lambda: get("reload_hosts")(),
            safe_host_inventory_entry=lambda host, **kwargs: get("safe_host_inventory_entry")(
                host,
                **kwargs,
            ),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_host_update_blueprint(
            update_host=lambda host_name, payload: get("update_dynamic_host")(
                host_name,
                payload,
            ),
            reload_hosts=lambda: get("reload_hosts")(),
            safe_host_inventory_entry=lambda host, **kwargs: get("safe_host_inventory_entry")(
                host,
                **kwargs,
            ),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_winrm_trust_preview_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name),
            read_certificate_upload=lambda: get("_read_winrm_certificate_upload")(),
            parse_certificate=lambda raw: get("_parse_winrm_certificate_bytes")(raw),
            response_metadata=lambda certificate, host, input_format: get(
                "_winrm_certificate_response_metadata"
            )(certificate, host, input_format),
            validate_certificate=lambda certificate, host: get("_validate_winrm_certificate")(
                certificate,
                host,
            ),
            request_id=lambda: get("_request_id")(),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=lambda host_name, code: get("_winrm_trust_error_payload")(
                host_name,
                code,
            ),
            trust_http_status=lambda code: get("_winrm_trust_http_status")(code),
            internal_error_response=lambda message, exc: get("internal_error_response")(
                message,
                exc,
            ),
        )
    )
    app.register_blueprint(
        create_winrm_trust_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name),
            inspect_trust=lambda host: get("inspect_winrm_trust")(host),
            request_id=lambda: get("_request_id")(),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=lambda host_name, code: get("_winrm_trust_error_payload")(
                host_name,
                code,
            ),
            trust_http_status=lambda code: get("_winrm_trust_http_status")(code),
            internal_error_response=lambda message, exc: get("internal_error_response")(
                message,
                exc,
            ),
        )
    )
    app.register_blueprint(
        create_winrm_trust_mutation_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name),
            request_value=lambda name: get("_winrm_trust_request_value")(name),
            normalize_trust_ref=lambda value: get("normalize_winrm_trust_ref")(value),
            trust_ref_for_host=lambda host: get("winrm_trust_ref_for_host")(host),
            read_certificate_upload=lambda: get("_read_winrm_certificate_upload")(),
            parse_certificate=lambda raw: get("_parse_winrm_certificate_bytes")(raw),
            validate_certificate=lambda certificate, host: get("_validate_winrm_certificate")(
                certificate,
                host,
            ),
            store_trust=lambda host, certificate: get("_store_winrm_trust_certificate")(
                host,
                certificate,
            ),
            delete_trust=lambda host: get("_delete_winrm_trust_certificate")(host),
            inspect_trust=lambda host: get("inspect_winrm_trust")(host),
            request_id=lambda: get("_request_id")(),
            sanitize_log_value=lambda value: get("_sanitize_log_value")(value),
            log_info=lambda *args, **kwargs: get("logging").info(*args, **kwargs),
            log_warning=lambda *args, **kwargs: get("logging").warning(*args, **kwargs),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=lambda host_name, code: get("_winrm_trust_error_payload")(
                host_name,
                code,
            ),
            trust_http_status=lambda code: get("_winrm_trust_http_status")(code),
            fingerprint_confirmation_required_message=get(
                "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE"
            ),
            fingerprint_mismatch_message=get("WINRM_FINGERPRINT_MISMATCH_MESSAGE"),
            trust_ref_mismatch_message=get("WINRM_TRUST_REF_MISMATCH_MESSAGE"),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_winrm_credentials_blueprint(
            save_credentials=lambda credential_ref, user, password: get("save_winrm_credentials")(
                credential_ref,
                user,
                password,
            ),
            reload_hosts=lambda: get("reload_hosts")(),
            normalize_credential_ref=lambda value: get("normalize_credential_ref")(value),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_hosts_reload_blueprint(
            reload_hosts=lambda: get("reload_hosts")(),
        )
    )
    app.register_blueprint(
        create_aas_sync_blueprint(
            find_host=lambda host_name: get("HOSTS").get(host_name),
            resolve_lab_ids_for_host=lambda host: get("resolve_lab_ids_for_host")(host),
            sync_lab=lambda lab_id, host: get("aas_generator").sync_lab_to_basyx(lab_id, host),
            log_failure=lambda *args: get("logging").exception(*args),
        )
    )
    app.register_blueprint(
        create_local_mode_blueprint(
            parse_bool=lambda value, default: get("parse_bool")(value, default),
            find_host=lambda host_name: get("HOSTS").get(host_name),
            get_flag_path=lambda host: get("get_local_mode_flag_path")(host),
            write_remote_file=lambda *args: get("write_remote_file")(*args),
            remove_remote_file=lambda *args: get("remove_remote_file")(*args),
            internal_error_response=lambda *args, **kwargs: get("internal_error_response")(
                *args,
                **kwargs,
            ),
        )
    )
    app.register_blueprint(
        create_operations_blueprint(
            get_db_engine=lambda: get("DB_ENGINE"),
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            sanitize_limit=lambda value: get("_sanitize_limit")(value),
            sanitize_offset=lambda value: get("_sanitize_offset")(value),
            sql_text=lambda statement: get("text")(statement),
            rows_to_operations=lambda rows: get("_rows_to_operations")(rows),
            internal_error_response=lambda message, exc: get("internal_error_response")(
                message,
                exc,
            ),
        )
    )
    app.register_blueprint(
        create_aas_lab_sync_blueprint(
            resolve_host_by_lab=lambda lab_id: get("resolve_host_by_lab")(lab_id),
            parse_bool=lambda value, default: get("parse_bool")(value, default),
            poll_heartbeat=lambda host, include_events: get("poll_heartbeat")(
                host,
                include_events=include_events,
            ),
            load_persisted_heartbeat=lambda lab_id, host: get("_load_aas_persisted_heartbeat")(
                lab_id,
                host,
            )
            if get("DB_ENGINE")
            else None,
            sync_lab=lambda lab_id, host, heartbeat, metadata: get("aas_generator").sync_lab_to_basyx(
                lab_id,
                host,
                heartbeat,
                metadata,
            ),
            log_warning=lambda *args, **kwargs: get("logging").warning(*args, **kwargs),
        )
    )
    app.register_blueprint(
        create_internal_ingest_blueprint(
            ingest_token=lambda: get("SESSION_OBSERVATION_INGEST_TOKEN"),
            compare_digest=lambda provided, expected: get("hmac").compare_digest(
                provided,
                expected,
            ),
            enqueue_revocation=lambda payload: get("enqueue_guacamole_token_revocation")(
                payload
            ),
            enqueue_observation=lambda payload: get("enqueue_session_observation")(payload),
        )
    )
