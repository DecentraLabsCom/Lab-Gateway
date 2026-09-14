from pathlib import Path

import worker


def test_guacamole_temp_user_cleanup_default_interval_is_900_seconds():
    assert worker.GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS == 900


def test_ops_worker_image_copies_the_dedicated_error_contract_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY errors.py /app/errors.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_flask_application_hooks_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY app_hooks.py /app/app_hooks.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_flask_application_factory_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY app_factory.py /app/app_factory.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_process_entrypoint_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY entrypoint.py /app/entrypoint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_process_entrypoint_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY entrypoint_runtime.py /app/entrypoint_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_config_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_config.py /app/runtime_config.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_legacy_api_compatibility_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY legacy_api.py /app/legacy_api.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_context_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_context.py /app/runtime_context.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_composition_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_composition.py /app/runtime_composition.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_values.py /app/runtime_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_secret_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY secret_values.py /app/secret_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_state_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_state.py /app/runtime_state.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_worker_compatibility_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY worker_compatibility_runtime.py /app/worker_compatibility_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_config_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_config_runtime.py /app/host_config_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_discovery_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_discovery_runtime.py /app/host_discovery_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_provisioning_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_provisioning_runtime.py /app/host_provisioning_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_runtime.py /app/guacamole_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_inventory_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_inventory_runtime.py /app/host_inventory_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_runtime.py /app/heartbeat_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_lifecycle_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_lifecycle_runtime.py /app/reservation_lifecycle_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_timeline_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY timeline_runtime.py /app/timeline_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_credential_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY credential_runtime.py /app/credential_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_app_hooks_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY app_hooks_runtime.py /app/app_hooks_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_database_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY database_runtime.py /app/database_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_input_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY input_runtime.py /app/input_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_reload_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_reload_runtime.py /app/host_reload_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_scheduler_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY scheduler_runtime.py /app/scheduler_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_runtime_services_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY runtime_services.py /app/runtime_services.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_power_runtime_factory_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY power_runtime_factory.py /app/power_runtime_factory.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_demo_readiness_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY demo_readiness_service.py /app/demo_readiness_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_catalog_io_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_catalog_io.py /app/host_catalog_io.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_credential_store_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_credential_store.py /app/winrm_credential_store.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_scheduler_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY scheduler_service.py /app/scheduler_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_wol_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY wol_service.py /app/wol_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_wol_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY wol_runtime.py /app/wol_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_network_probe_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY network_probe.py /app/network_probe.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_operation_persistence_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY operation_persistence.py /app/operation_persistence.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_notification_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY notification_service.py /app/notification_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_persistence_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_persistence.py /app/heartbeat_persistence.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_timeline_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY timeline_service.py /app/timeline_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_provision_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_provision_service.py /app/guacamole_provision_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_orchestrator_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_orchestrator.py /app/reservation_orchestrator.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_runtime.py /app/reservation_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_runtime.py /app/winrm_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_session_observations_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY session_observations.py /app/session_observations.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_session_observation_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY session_observation_runtime.py /app/session_observation_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_operations_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_operations.py /app/reservation_operations.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_execution_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_execution_runtime.py /app/reservation_execution_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_demo_operations_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY demo_operations.py /app/demo_operations.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_demo_runtime_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY demo_runtime.py /app/demo_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_reservation_steps_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY reservation_steps.py /app/reservation_steps.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_power_reservation_service_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY power_reservation_service.py /app/power_reservation_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_operations_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_operations.py /app/winrm_trust_operations.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_pure_winrm_trust_helpers():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust.py /app/winrm_trust.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_store_helpers():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_store.py /app/winrm_trust_store.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_service.py /app/winrm_trust_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_runtime():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_runtime.py /app/winrm_trust_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_session_policy():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_session_policy.py /app/winrm_session_policy.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_datetime_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY datetime_values.py /app/datetime_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_input_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY input_values.py /app/input_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_database_health_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY database_health.py /app/database_health.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_demo_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY demo_values.py /app/demo_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_operation_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY operation_values.py /app/operation_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_health_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY health_values.py /app/health_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_operations_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY operations_route.py /app/operations_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_route.py /app/hosts_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_blueprint.py /app/hosts_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_operations_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY operations_blueprint.py /app/operations_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_timeline_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY timeline_blueprint.py /app/timeline_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_health_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY health_blueprint.py /app/health_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_connections_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_connections_blueprint.py /app/guacamole_connections_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_blueprint.py /app/winrm_trust_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_reload_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_reload_route.py /app/hosts_reload_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_reload_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_reload_blueprint.py /app/hosts_reload_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_discover_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_discover_route.py /app/hosts_discover_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_hosts_discover_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY hosts_discover_blueprint.py /app/hosts_discover_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_aas_sync_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY aas_sync_route.py /app/aas_sync_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_timeline_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY timeline_route.py /app/timeline_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_route.py /app/winrm_trust_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_preview_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_preview_route.py /app/winrm_trust_preview_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_preview_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_preview_blueprint.py /app/winrm_trust_preview_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_credentials_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_credentials_route.py /app/winrm_credentials_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_credentials_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_credentials_blueprint.py /app/winrm_credentials_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_local_mode_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY local_mode_route.py /app/local_mode_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_local_mode_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY local_mode_blueprint.py /app/local_mode_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_mutation_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_mutation_route.py /app/winrm_trust_mutation_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_mutation_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_mutation_blueprint.py /app/winrm_trust_mutation_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_update_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_update_route.py /app/host_update_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_update_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_update_blueprint.py /app/host_update_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_provision_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_provision_route.py /app/host_provision_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_provision_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_provision_blueprint.py /app/host_provision_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_aas_lab_sync_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY aas_lab_sync_route.py /app/aas_lab_sync_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_aas_lab_sync_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY aas_lab_sync_blueprint.py /app/aas_lab_sync_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_internal_ingest_routes():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY internal_ingest_routes.py /app/internal_ingest_routes.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_internal_ingest_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY internal_ingest_blueprint.py /app/internal_ingest_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_internal_ingest_runtime():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY internal_ingest_runtime.py /app/internal_ingest_runtime.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_lifecycle_routes():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY lifecycle_routes.py /app/lifecycle_routes.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_lifecycle_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY lifecycle_blueprint.py /app/lifecycle_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_wol_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY wol_route.py /app/wol_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_route.py /app/winrm_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_physical_operations_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY physical_operations_blueprint.py /app/physical_operations_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_session_factory():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_session_factory.py /app/winrm_session_factory.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_execution_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_execution.py /app/winrm_command_execution.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_builders():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_builders.py /app/winrm_command_builders.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_service.py /app/winrm_command_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_values.py /app/heartbeat_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_service.py /app/heartbeat_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_stream():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_stream.py /app/heartbeat_stream.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_poller():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_poller.py /app/heartbeat_poller.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_route.py /app/heartbeat_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_poll_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_poll_blueprint.py /app/heartbeat_poll_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_stream_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_stream_blueprint.py /app/heartbeat_stream_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_stream_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_stream_route.py /app/heartbeat_stream_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_heartbeat_discovery():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_heartbeat_discovery.py /app/host_heartbeat_discovery.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_heartbeat_paths():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_heartbeat_paths.py /app/host_heartbeat_paths.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_connection_lookup():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_connection_lookup.py /app/guacamole_connection_lookup.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_connection_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_connection_values.py /app/guacamole_connection_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_connection_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_connection_route.py /app/guacamole_connection_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_cleanup_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_cleanup_route.py /app/guacamole_cleanup_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_provision_route():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_provision_route.py /app/guacamole_provision_route.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_provision_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_provision_blueprint.py /app/guacamole_provision_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_aas_sync_blueprint():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY aas_sync_blueprint.py /app/aas_sync_blueprint.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_catalog_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_catalog_service.py /app/guacamole_catalog_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_guacamole_dsn_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY guacamole_dsn.py /app/guacamole_dsn.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_ops_dsn_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY ops_dsn.py /app/ops_dsn.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_catalog_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_catalog.py /app/host_catalog.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_registry_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_registry.py /app/host_registry.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_config_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_config_service.py /app/host_config_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_reload_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_reload_service.py /app/host_reload_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_inventory_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_inventory_values.py /app/host_inventory_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_inventory_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_inventory_service.py /app/host_inventory_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_discovery_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_discovery_values.py /app/host_discovery_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_discovery_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_discovery_service.py /app/host_discovery_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_provisioning_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_provisioning_values.py /app/host_provisioning_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_winrm_credentials_resolution():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_credentials_resolution.py /app/winrm_credentials_resolution.py" in dockerfile.read_text(encoding="utf-8")


def test_main_starts_scheduler_and_serves_with_waitress(monkeypatch):
    calls = []

    monkeypatch.setenv("OPS_BIND", "127.0.0.1")
    monkeypatch.setenv("OPS_PORT", "9876")
    monkeypatch.setattr(worker, "start_scheduler", lambda: calls.append("scheduler"))
    monkeypatch.setattr(
        worker,
        "serve",
        lambda app, host, port: calls.append((app, host, port)),
    )

    worker.main()

    assert calls == ["scheduler", (worker.APP, "127.0.0.1", 9876)]
