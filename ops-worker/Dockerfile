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
COPY errors.py /app/errors.py
COPY winrm_trust.py /app/winrm_trust.py
COPY winrm_trust_store.py /app/winrm_trust_store.py
COPY winrm_trust_service.py /app/winrm_trust_service.py
COPY winrm_session_policy.py /app/winrm_session_policy.py
COPY datetime_values.py /app/datetime_values.py
COPY input_values.py /app/input_values.py
COPY database_health.py /app/database_health.py
COPY demo_values.py /app/demo_values.py
COPY operation_values.py /app/operation_values.py
COPY health_values.py /app/health_values.py
COPY operations_route.py /app/operations_route.py
COPY hosts_route.py /app/hosts_route.py
COPY hosts_reload_route.py /app/hosts_reload_route.py
COPY hosts_discover_route.py /app/hosts_discover_route.py
COPY timeline_route.py /app/timeline_route.py
COPY aas_sync_route.py /app/aas_sync_route.py
COPY winrm_trust_route.py /app/winrm_trust_route.py
COPY winrm_session_factory.py /app/winrm_session_factory.py
COPY winrm_command_execution.py /app/winrm_command_execution.py
COPY winrm_command_builders.py /app/winrm_command_builders.py
COPY winrm_command_service.py /app/winrm_command_service.py
COPY heartbeat_values.py /app/heartbeat_values.py
COPY heartbeat_service.py /app/heartbeat_service.py
COPY heartbeat_stream.py /app/heartbeat_stream.py
COPY heartbeat_poller.py /app/heartbeat_poller.py
COPY heartbeat_route.py /app/heartbeat_route.py
COPY heartbeat_stream_route.py /app/heartbeat_stream_route.py
COPY host_heartbeat_discovery.py /app/host_heartbeat_discovery.py
COPY host_heartbeat_paths.py /app/host_heartbeat_paths.py
COPY guacamole_connection_lookup.py /app/guacamole_connection_lookup.py
COPY guacamole_connection_values.py /app/guacamole_connection_values.py
COPY guacamole_connection_route.py /app/guacamole_connection_route.py
COPY guacamole_cleanup_route.py /app/guacamole_cleanup_route.py
COPY guacamole_provision_route.py /app/guacamole_provision_route.py
COPY guacamole_catalog_service.py /app/guacamole_catalog_service.py
COPY guacamole_dsn.py /app/guacamole_dsn.py
COPY ops_dsn.py /app/ops_dsn.py
COPY host_catalog.py /app/host_catalog.py
COPY host_registry.py /app/host_registry.py
COPY host_config_service.py /app/host_config_service.py
COPY host_reload_service.py /app/host_reload_service.py
COPY host_inventory_values.py /app/host_inventory_values.py
COPY host_inventory_service.py /app/host_inventory_service.py
COPY host_discovery_values.py /app/host_discovery_values.py
COPY host_discovery_service.py /app/host_discovery_service.py
COPY host_provisioning_values.py /app/host_provisioning_values.py
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
