"""Compatibility facades kept while the Flask handlers live in Blueprints."""

from collections.abc import Callable, Mapping
from typing import Any

from heartbeat_route import handle_heartbeat_poll as _handle_heartbeat_poll
from heartbeat_stream_route import handle_heartbeat_stream as _handle_heartbeat_stream
from host_provision_route import handle_host_provision as _handle_host_provision
from host_update_route import handle_host_update as _handle_host_update
from hosts_discover_route import handle_hosts_discover as _handle_hosts_discover
from hosts_reload_route import handle_hosts_reload as _handle_hosts_reload
from hosts_route import handle_hosts_inventory as _handle_hosts_inventory
from guacamole_cleanup_route import handle_guacamole_cleanup as _handle_guacamole_cleanup
from guacamole_connection_route import handle_guacamole_connections as _handle_guacamole_connections
from guacamole_provision_route import handle_guacamole_provision as _handle_guacamole_provision
from lifecycle_routes import handle_lifecycle_request as _handle_lifecycle_request
from local_mode_route import handle_local_mode as _handle_local_mode
from operations_route import handle_operations_recent as _handle_operations_recent
from timeline_route import handle_reservation_timeline as _handle_reservation_timeline
from winrm_credentials_route import handle_winrm_credentials as _handle_winrm_credentials
from winrm_route import handle_winrm as _handle_winrm
from winrm_trust_mutation_route import (
    handle_winrm_trust_delete as _handle_winrm_trust_delete,
    handle_winrm_trust_put as _handle_winrm_trust_put,
)
from winrm_trust_preview_route import handle_winrm_trust_preview as _handle_winrm_trust_preview
from winrm_trust_route import handle_winrm_trust_get as _handle_winrm_trust_get
from wol_route import handle_wol as _handle_wol
from aas_lab_sync_route import handle_aas_lab_sync as _handle_aas_lab_sync
from aas_sync_route import handle_aas_sync as _handle_aas_sync


LEGACY_API_NAMES = (
    "api_wol",
    "api_winrm",
    "api_poll_heartbeat",
    "api_stream_heartbeat",
    "api_reservation_start",
    "api_reservation_end",
    "api_demo_start",
    "api_demo_event",
    "api_demo_end",
    "api_reservation_timeline",
    "api_hosts_inventory",
    "api_internal_guacamole_connections",
    "api_internal_guacamole_provision",
    "api_internal_guacamole_delete",
    "api_hosts_discover",
    "api_hosts_provision",
    "api_hosts_update",
    "api_preview_winrm_trust",
    "api_get_winrm_trust",
    "api_save_winrm_trust",
    "api_delete_winrm_trust",
    "api_save_winrm_credentials",
    "api_hosts_reload",
    "api_aas_sync",
    "api_hosts_local_mode",
    "api_operations_recent",
    "api_aas_sync_lab",
    "health",
)


def create_legacy_api(providers: Mapping[str, Any]) -> dict[str, Callable[..., Any]]:
    """Build the historical ``api_*`` callables from a live worker namespace."""
    get = providers.__getitem__
    def api_wol():
        return _handle_wol(
            get("request").get_json(force=True, silent=True) or {},
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            is_valid_ping_target=get("_is_valid_ping_target"),
            wol_and_wait=get("wol_and_wait"),
            now=get("time").time,
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_winrm():
        return _handle_winrm(
            get("request").get_json(force=True, silent=True) or {},
            allowed_commands=get("ALLOWED_WINRM_COMMANDS"),
            find_host=lambda host_name: get("HOSTS").get(host_name),
            run_command=get("run_labstation_command"),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_poll_heartbeat():
        return _handle_heartbeat_poll(
            get("request").get_json(force=True, silent=True) or {},
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            poll_heartbeat=get("poll_heartbeat"),
            now=get("time").time,
            jsonify=get("jsonify"),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            missing_credentials_predicate=get("is_missing_winrm_credentials_error"),
            credentials_required_message=get("WINRM_CREDENTIALS_REQUIRED_MESSAGE"),
            internal_error_response=get("internal_error_response"),
        )

    def api_stream_heartbeat():
        return _handle_heartbeat_stream(
            get("request").args,
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            generate_stream=get("generate_heartbeat_stream"),
            response_factory=get("Response"),
            stream_with_context=get("stream_with_context"),
            jsonify=get("jsonify"),
        )

    def api_reservation_start():
        return _handle_lifecycle_request(
            get("request").get_json(force=True, silent=True) or {},
            operation=get("handle_reservation_start"),
            jsonify=get("jsonify"),
        )

    def api_reservation_end():
        return _handle_lifecycle_request(
            get("request").get_json(force=True, silent=True) or {},
            operation=get("handle_reservation_end"),
            jsonify=get("jsonify"),
        )

    def api_demo_start():
        return _handle_lifecycle_request(
            get("request").get_json(force=True, silent=True) or {},
            operation=get("handle_demo_start"),
            jsonify=get("jsonify"),
        )

    def api_demo_event():
        return _handle_lifecycle_request(
            get("request").get_json(force=True, silent=True) or {},
            operation=get("handle_demo_event"),
            jsonify=get("jsonify"),
        )

    def api_demo_end():
        return _handle_lifecycle_request(
            get("request").get_json(force=True, silent=True) or {},
            operation=get("handle_demo_end"),
            jsonify=get("jsonify"),
        )

    def api_reservation_timeline():
        return _handle_reservation_timeline(
            get("request").args,
            db_engine=get("DB_ENGINE"),
            sanitize_limit=get("_sanitize_limit"),
            sanitize_offset=get("_sanitize_offset"),
            build_timeline=get("build_reservation_timeline"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_hosts_inventory():
        return _handle_hosts_inventory(
            build_inventory=get("build_host_inventory"),
            jsonify=get("jsonify"),
        )

    def api_internal_guacamole_connections():
        return _handle_guacamole_connections(
            authorize=get("require_guacamole_provisioner_auth"),
            load_connections=get("load_guacamole_connections"),
            safe_connection_response=get("safe_connection_response"),
            jsonify=get("jsonify"),
        )

    def api_internal_guacamole_provision():
        return _handle_guacamole_provision(
            get("request").get_json(silent=True) or {},
            authorize=get("require_guacamole_provisioner_auth"),
            provision_temporary_user=get("provision_guacamole_temporary_user"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_internal_guacamole_delete(session_id: str):
        return _handle_guacamole_cleanup(
            session_id,
            authorize=get("require_guacamole_provisioner_auth"),
            delete_temporary_user=get("delete_guacamole_temporary_user"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_hosts_discover():
        return _handle_hosts_discover(
            get("request").get_json(force=True, silent=True) or {},
            resolve_connection=get("resolve_guacamole_connection"),
            discover_candidate=get("discover_labstation_candidate"),
            jsonify=get("jsonify"),
        )

    def api_hosts_provision():
        return _handle_host_provision(
            get("request").get_json(force=True, silent=True) or {},
            resolve_connection=get("resolve_guacamole_connection"),
            discover_candidate=get("discover_labstation_candidate"),
            enough_discovery_signals=get("ENOUGH_DISCOVERY_SIGNALS"),
            build_host=get("build_provisioned_host"),
            find_host=get("HOSTS").get,
            upsert_host=get("upsert_dynamic_host"),
            reload_hosts=get("reload_hosts"),
            safe_host_inventory_entry=get("safe_host_inventory_entry"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_hosts_update(host_name: str):
        return _handle_host_update(
            host_name,
            get("request").get_json(force=True, silent=True) or {},
            update_host=get("update_dynamic_host"),
            reload_hosts=get("reload_hosts"),
            safe_host_inventory_entry=get("safe_host_inventory_entry"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_preview_winrm_trust(host_name: str):
        return _handle_winrm_trust_preview(
            host_name,
            find_host=get("HOSTS").get,
            read_certificate_upload=get("_read_winrm_certificate_upload"),
            parse_certificate=get("_parse_winrm_certificate_bytes"),
            response_metadata=get("_winrm_certificate_response_metadata"),
            validate_certificate=get("_validate_winrm_certificate"),
            request_id=get("_request_id"),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            trust_http_status=get("_winrm_trust_http_status"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_get_winrm_trust(host_name: str):
        return _handle_winrm_trust_get(
            host_name,
            find_host=get("HOSTS").get,
            inspect_trust=get("inspect_winrm_trust"),
            request_id=get("_request_id"),
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            trust_http_status=get("_winrm_trust_http_status"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_save_winrm_trust(host_name: str):
        return _handle_winrm_trust_put(
            host_name,
            headers=get("request").headers,
            find_host=get("HOSTS").get,
            request_value=get("_winrm_trust_request_value"),
            normalize_trust_ref=get("normalize_winrm_trust_ref"),
            trust_ref_for_host=get("winrm_trust_ref_for_host"),
            read_certificate_upload=get("_read_winrm_certificate_upload"),
            parse_certificate=get("_parse_winrm_certificate_bytes"),
            validate_certificate=get("_validate_winrm_certificate"),
            store_trust=get("_store_winrm_trust_certificate"),
            request_id=get("_request_id"),
            sanitize_log_value=get("_sanitize_log_value"),
            log_info=get("logging").info,
            log_warning=get("logging").warning,
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            trust_http_status=get("_winrm_trust_http_status"),
            fingerprint_confirmation_required_message=get(
                "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE"
            ),
            fingerprint_mismatch_message=get("WINRM_FINGERPRINT_MISMATCH_MESSAGE"),
            trust_ref_mismatch_message=get("WINRM_TRUST_REF_MISMATCH_MESSAGE"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_delete_winrm_trust(host_name: str):
        return _handle_winrm_trust_delete(
            host_name,
            find_host=get("HOSTS").get,
            delete_trust=get("_delete_winrm_trust_certificate"),
            inspect_trust=get("inspect_winrm_trust"),
            request_id=get("_request_id"),
            sanitize_log_value=get("_sanitize_log_value"),
            log_info=get("logging").info,
            trust_error_type=get("WinRMTrustError"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            trust_http_status=get("_winrm_trust_http_status"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_save_winrm_credentials():
        return _handle_winrm_credentials(
            get("request").get_json(force=True, silent=True) or {},
            save_credentials=get("save_winrm_credentials"),
            reload_hosts=get("reload_hosts"),
            normalize_credential_ref=get("normalize_credential_ref"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_hosts_reload():
        return _handle_hosts_reload(
            reload_hosts=get("reload_hosts"),
            jsonify=get("jsonify"),
        )

    def api_aas_sync():
        return _handle_aas_sync(
            get("request").get_json(force=True, silent=True) or {},
            find_host=get("HOSTS").get,
            sync_lab=get("aas_generator").sync_lab_to_basyx,
            log_failure=get("logging").exception,
            jsonify=get("jsonify"),
        )

    def api_hosts_local_mode():
        return _handle_local_mode(
            get("request").get_json(force=True, silent=True) or {},
            parse_bool=get("parse_bool"),
            find_host=get("HOSTS").get,
            get_flag_path=get("get_local_mode_flag_path"),
            write_remote_file=get("write_remote_file"),
            remove_remote_file=get("remove_remote_file"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_operations_recent():
        return _handle_operations_recent(
            get("request").args,
            db_engine=get("DB_ENGINE"),
            find_host=lambda host_name: get("HOSTS").get(host_name) if host_name else None,
            sanitize_limit=get("_sanitize_limit"),
            sanitize_offset=get("_sanitize_offset"),
            sql_text=get("text"),
            rows_to_operations=get("_rows_to_operations"),
            jsonify=get("jsonify"),
            internal_error_response=get("internal_error_response"),
        )

    def api_aas_sync_lab(lab_id: str):
        return _handle_aas_lab_sync(
            lab_id,
            get("request").get_json(silent=True) or {},
            find_host_by_lab=get("HOSTS").get_by_lab,
            parse_bool=get("parse_bool"),
            poll_heartbeat=get("poll_heartbeat"),
            load_persisted_heartbeat=get("_load_aas_persisted_heartbeat")
            if get("DB_ENGINE")
            else None,
            sync_lab=get("aas_generator").sync_lab_to_basyx,
            log_warning=get("logging").warning,
            jsonify=get("jsonify"),
        )

    def health():
        db_engine = get("DB_ENGINE")
        db_ok = get("database_is_usable")(db_engine, "SELECT 1")
        fernet_ok = get("fernet_key_is_usable")()
        guacamole_schema_ok = get("database_is_usable")(
            get("GUACAMOLE_DB_ENGINE"),
            """
            SELECT 1
            FROM guacamole_entity e
            LEFT JOIN guacamole_user u ON u.entity_id = e.entity_id
            LEFT JOIN guacamole_connection_permission cp ON cp.entity_id = e.entity_id
            LEFT JOIN guacamole_connection c ON c.connection_id = cp.connection_id
            LIMIT 1
            """,
        )
        failed_revocations = None
        failed_observations = None
        health_db_engine = db_engine
        if db_ok and health_db_engine:
            try:
                with health_db_engine.connect() as conn:
                    failed_revocations = int(conn.execute(get("text")(
                        "SELECT COUNT(*) FROM guacamole_token_revocation_queue WHERE status = 'FAILED'"
                    )).scalar_one())
                    failed_observations = int(conn.execute(get("text")(
                        "SELECT COUNT(*) FROM gateway_session_observation_outbox WHERE status = 'FAILED'"
                    )).scalar_one())
            except Exception as exc:  # pylint: disable=broad-except
                get("logging").warning("Health durable queue check failed: %s", exc)
        payload, status = get("_build_health_response_impl")(
            hosts_loaded=len(get("HOSTS").all_hosts()),
            db_ok=db_ok,
            fernet_ok=fernet_ok,
            guacamole_schema_ok=guacamole_schema_ok,
            failed_revocations=failed_revocations,
            failed_observations=failed_observations,
            demo=get("demo_readiness")(),
        )
        return get("jsonify")(payload), status

    functions = locals()
    return {name: functions[name] for name in LEGACY_API_NAMES}
