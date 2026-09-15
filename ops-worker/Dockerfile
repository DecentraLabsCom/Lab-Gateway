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

# Keep the image layer graph shallow: the runtime is composed of top-level
# Python modules plus the power integration package.
COPY *.py /app/
COPY power /app/power

RUN groupadd --gid "${OPS_GID}" opsworker \
    && useradd --uid "${OPS_UID}" --gid "${OPS_GID}" --create-home --shell /usr/sbin/nologin opsworker \
    && mkdir -p /app/data \
    && chown -R opsworker:opsworker /app

USER opsworker

CMD ["python", "-m", "worker"]
