FROM mirror.gcr.io/library/python:3.12-slim
RUN python -m pip install --no-cache-dir \
    paramiko==5.0.0 \
    requests==2.34.2
WORKDIR /workspace
COPY test_gateway_station_ssh_e2e.py /tests/test_gateway_station_ssh_e2e.py
