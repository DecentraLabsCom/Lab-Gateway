FROM python:3.11-slim

WORKDIR /app

# Build the runtime identity to match the host UID/GID used by the persistent
# ops-data bind mount. The application never runs as root.
ARG OPS_UID=1000
ARG OPS_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPS_BIND=0.0.0.0 \
    OPS_PORT=8081 \
    OPS_CONFIG=/app/hosts.json

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY worker.py /app/worker.py
COPY app_factory.py /app/app_factory.py
COPY entrypoint.py /app/entrypoint.py
COPY entrypoint_runtime.py /app/entrypoint_runtime.py
COPY app_hooks.py /app/app_hooks.py
COPY app_hooks_runtime.py /app/app_hooks_runtime.py
COPY runtime_context.py /app/runtime_context.py
COPY runtime_composition.py /app/runtime_composition.py
COPY runtime_values.py /app/runtime_values.py
COPY secret_values.py /app/secret_values.py
COPY runtime_config.py /app/runtime_config.py
COPY runtime_state.py /app/runtime_state.py
COPY worker_compatibility_runtime.py /app/worker_compatibility_runtime.py
COPY runtime_services.py /app/runtime_services.py
COPY power_runtime_factory.py /app/power_runtime_factory.py
COPY demo_readiness_service.py /app/demo_readiness_service.py
COPY host_catalog_io.py /app/host_catalog_io.py
COPY winrm_credential_store.py /app/winrm_credential_store.py
COPY credential_runtime.py /app/credential_runtime.py
COPY scheduler_service.py /app/scheduler_service.py
COPY scheduler_runtime.py /app/scheduler_runtime.py
COPY wol_service.py /app/wol_service.py
COPY wol_runtime.py /app/wol_runtime.py
COPY network_probe.py /app/network_probe.py
COPY operation_persistence.py /app/operation_persistence.py
COPY notification_service.py /app/notification_service.py
COPY heartbeat_persistence.py /app/heartbeat_persistence.py
COPY timeline_service.py /app/timeline_service.py
COPY timeline_runtime.py /app/timeline_runtime.py
COPY guacamole_provision_service.py /app/guacamole_provision_service.py
COPY reservation_orchestrator.py /app/reservation_orchestrator.py
COPY reservation_runtime.py /app/reservation_runtime.py
COPY winrm_runtime.py /app/winrm_runtime.py
COPY session_observations.py /app/session_observations.py
COPY session_observation_runtime.py /app/session_observation_runtime.py
COPY session_observation_maintenance.py /app/session_observation_maintenance.py
COPY reservation_operations.py /app/reservation_operations.py
COPY reservation_lifecycle_runtime.py /app/reservation_lifecycle_runtime.py
COPY reservation_execution_runtime.py /app/reservation_execution_runtime.py
COPY demo_operations.py /app/demo_operations.py
COPY demo_runtime.py /app/demo_runtime.py
COPY reservation_steps.py /app/reservation_steps.py
COPY power_reservation_service.py /app/power_reservation_service.py
COPY winrm_trust_operations.py /app/winrm_trust_operations.py
COPY errors.py /app/errors.py
COPY winrm_trust.py /app/winrm_trust.py
COPY winrm_trust_store.py /app/winrm_trust_store.py
COPY winrm_trust_service.py /app/winrm_trust_service.py
COPY winrm_trust_runtime.py /app/winrm_trust_runtime.py
COPY winrm_session_policy.py /app/winrm_session_policy.py
COPY datetime_values.py /app/datetime_values.py
COPY input_values.py /app/input_values.py
COPY input_runtime.py /app/input_runtime.py
COPY database_health.py /app/database_health.py
COPY database_runtime.py /app/database_runtime.py
COPY demo_values.py /app/demo_values.py
COPY operation_values.py /app/operation_values.py
COPY health_values.py /app/health_values.py
COPY health_blueprint.py /app/health_blueprint.py
COPY operations_route.py /app/operations_route.py
COPY hosts_route.py /app/hosts_route.py
COPY hosts_blueprint.py /app/hosts_blueprint.py
COPY hosts_reload_route.py /app/hosts_reload_route.py
COPY hosts_reload_blueprint.py /app/hosts_reload_blueprint.py
COPY operations_blueprint.py /app/operations_blueprint.py
COPY timeline_blueprint.py /app/timeline_blueprint.py
COPY hosts_discover_route.py /app/hosts_discover_route.py
COPY hosts_discover_blueprint.py /app/hosts_discover_blueprint.py
COPY timeline_route.py /app/timeline_route.py
COPY aas_sync_route.py /app/aas_sync_route.py
COPY aas_sync_blueprint.py /app/aas_sync_blueprint.py
COPY winrm_trust_route.py /app/winrm_trust_route.py
COPY winrm_trust_blueprint.py /app/winrm_trust_blueprint.py
COPY winrm_trust_preview_route.py /app/winrm_trust_preview_route.py
COPY winrm_trust_preview_blueprint.py /app/winrm_trust_preview_blueprint.py
COPY winrm_credentials_route.py /app/winrm_credentials_route.py
COPY winrm_credentials_blueprint.py /app/winrm_credentials_blueprint.py
COPY local_mode_route.py /app/local_mode_route.py
COPY local_mode_blueprint.py /app/local_mode_blueprint.py
COPY winrm_trust_mutation_route.py /app/winrm_trust_mutation_route.py
COPY winrm_trust_mutation_blueprint.py /app/winrm_trust_mutation_blueprint.py
COPY host_update_route.py /app/host_update_route.py
COPY host_update_blueprint.py /app/host_update_blueprint.py
COPY host_provision_route.py /app/host_provision_route.py
COPY host_provision_blueprint.py /app/host_provision_blueprint.py
COPY aas_lab_sync_route.py /app/aas_lab_sync_route.py
COPY aas_lab_sync_blueprint.py /app/aas_lab_sync_blueprint.py
COPY internal_ingest_routes.py /app/internal_ingest_routes.py
COPY internal_ingest_blueprint.py /app/internal_ingest_blueprint.py
COPY internal_ingest_runtime.py /app/internal_ingest_runtime.py
COPY lifecycle_routes.py /app/lifecycle_routes.py
COPY lifecycle_blueprint.py /app/lifecycle_blueprint.py
COPY wol_route.py /app/wol_route.py
COPY winrm_route.py /app/winrm_route.py
COPY physical_operations_blueprint.py /app/physical_operations_blueprint.py
COPY winrm_session_factory.py /app/winrm_session_factory.py
COPY winrm_command_execution.py /app/winrm_command_execution.py
COPY winrm_command_builders.py /app/winrm_command_builders.py
COPY winrm_command_service.py /app/winrm_command_service.py
COPY heartbeat_values.py /app/heartbeat_values.py
COPY heartbeat_service.py /app/heartbeat_service.py
COPY heartbeat_stream.py /app/heartbeat_stream.py
COPY heartbeat_runtime.py /app/heartbeat_runtime.py
COPY heartbeat_poller.py /app/heartbeat_poller.py
COPY heartbeat_route.py /app/heartbeat_route.py
COPY heartbeat_poll_blueprint.py /app/heartbeat_poll_blueprint.py
COPY heartbeat_stream_route.py /app/heartbeat_stream_route.py
COPY heartbeat_stream_blueprint.py /app/heartbeat_stream_blueprint.py
COPY host_heartbeat_discovery.py /app/host_heartbeat_discovery.py
COPY host_heartbeat_paths.py /app/host_heartbeat_paths.py
COPY guacamole_connection_lookup.py /app/guacamole_connection_lookup.py
COPY guacamole_connection_values.py /app/guacamole_connection_values.py
COPY guacamole_connection_route.py /app/guacamole_connection_route.py
COPY guacamole_connections_blueprint.py /app/guacamole_connections_blueprint.py
COPY guacamole_cleanup_route.py /app/guacamole_cleanup_route.py
COPY guacamole_provision_route.py /app/guacamole_provision_route.py
COPY guacamole_provision_blueprint.py /app/guacamole_provision_blueprint.py
COPY guacamole_catalog_service.py /app/guacamole_catalog_service.py
COPY guacamole_runtime.py /app/guacamole_runtime.py
COPY guacamole_dsn.py /app/guacamole_dsn.py
COPY ops_dsn.py /app/ops_dsn.py
COPY host_catalog.py /app/host_catalog.py
COPY host_registry.py /app/host_registry.py
COPY host_config_service.py /app/host_config_service.py
COPY host_config_runtime.py /app/host_config_runtime.py
COPY host_reload_service.py /app/host_reload_service.py
COPY host_reload_runtime.py /app/host_reload_runtime.py
COPY host_inventory_values.py /app/host_inventory_values.py
COPY host_inventory_service.py /app/host_inventory_service.py
COPY host_inventory_runtime.py /app/host_inventory_runtime.py
COPY host_discovery_values.py /app/host_discovery_values.py
COPY host_discovery_service.py /app/host_discovery_service.py
COPY host_discovery_runtime.py /app/host_discovery_runtime.py
COPY host_provisioning_values.py /app/host_provisioning_values.py
COPY host_provisioning_runtime.py /app/host_provisioning_runtime.py
COPY winrm_credentials_resolution.py /app/winrm_credentials_resolution.py
COPY aas_generator.py /app/aas_generator.py
COPY rotate_secrets.py /app/rotate_secrets.py
COPY power_credentials.py /app/power_credentials.py
COPY power /app/power

RUN groupadd --gid "${OPS_GID}" opsworker \
    && useradd --uid "${OPS_UID}" --gid "${OPS_GID}" --create-home --shell /usr/sbin/nologin opsworker \
    && mkdir -p /app/data \
    && chown -R opsworker:opsworker /app

USER opsworker

CMD ["python", "-m", "worker"]
