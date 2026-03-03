FROM python:3.11-slim-bookworm

LABEL maintainer="Lab Gateway Team"
LABEL description="FMU Runner — FMI Co-Simulation execution service"

WORKDIR /app

# System deps required by FMPy (native libs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libxml2 \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN useradd -r -s /bin/false fmurunner

# Create writable directory for history DB
RUN mkdir -p /app/data && chown -R fmurunner:fmurunner /app/data

COPY . .

EXPOSE 8090

USER fmurunner

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
