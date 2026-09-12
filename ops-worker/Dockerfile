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
COPY winrm_session_factory.py /app/winrm_session_factory.py
COPY winrm_command_execution.py /app/winrm_command_execution.py
COPY winrm_command_builders.py /app/winrm_command_builders.py
COPY winrm_command_service.py /app/winrm_command_service.py
COPY heartbeat_values.py /app/heartbeat_values.py
COPY heartbeat_service.py /app/heartbeat_service.py
COPY heartbeat_stream.py /app/heartbeat_stream.py
COPY host_catalog.py /app/host_catalog.py
COPY host_registry.py /app/host_registry.py
COPY host_inventory_values.py /app/host_inventory_values.py
COPY host_discovery_values.py /app/host_discovery_values.py
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
