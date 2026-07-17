import os
import sys

import pytest
from flask.testing import FlaskClient
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# The production worker requires a gateway-injected credential on every
# operational API call.  Keep the existing direct test-client calls concise by
# injecting the test-only equivalent unless a test explicitly supplies a
# value (including an empty value to exercise rejection paths).
os.environ.setdefault("OPS_INTERNAL_AUTH_TOKEN", "test-ops-internal-token")
os.environ.setdefault("OPS_INTERNAL_AUTH_HEADER", "X-Ops-Internal-Token")
# AAS sync tests use HTTPS-shaped mock endpoints so the production endpoint
# policy is exercised without contacting a real external service.
os.environ.setdefault("AAS_ALLOWED_HOSTS", "127.0.0.1,basyx-mock,basyx-test")
os.environ.setdefault("AAS_SERVICE_TOKEN", "test-aas-service-token")

import worker


class OpsAuthenticatedTestClient(FlaskClient):
    def open(self, *args, **kwargs):
        headers = kwargs.get("headers")
        if headers is None:
            headers = {}
        else:
            headers = headers.copy()
        header_name = worker.OPS_INTERNAL_AUTH_HEADER
        if not any(str(key).lower() == header_name.lower() for key in headers):
            headers[header_name] = worker.OPS_INTERNAL_AUTH_TOKEN
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


worker.APP.test_client_class = OpsAuthenticatedTestClient


@pytest.fixture(scope="function")
def client():
    worker.APP.testing = True
    return worker.APP.test_client()


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    metadata = MetaData()

    Table(
        "auth_users",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("wallet_address", String(42), nullable=False, unique=True),
        Column("username", String(128)),
        Column("email", String(256)),
        Column("created_at", DateTime),
        Column("updated_at", DateTime),
        Column("is_active", Boolean, default=True),
    )

    Table(
        "lab_hosts",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(128), nullable=False, unique=True),
        Column("address", String(255), nullable=False),
        Column("mac", String(32)),
        Column("mode", String(16), default="pure"),
        Column("last_seen", DateTime),
        Column("created_at", DateTime),
        Column("updated_at", DateTime),
    )

    Table(
        "lab_host_heartbeat",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("host_id", Integer, nullable=False),
        Column("timestamp_utc", DateTime, nullable=False),
        Column("ready", Boolean),
        Column("local_mode", Boolean),
        Column("local_session", Boolean),
        Column("last_forced_logoff_ts", DateTime),
        Column("last_forced_logoff_user", String(128)),
        Column("last_power_action_ts", DateTime),
        Column("last_power_action_mode", String(32)),
        Column("raw_json", Text, nullable=False),
        Column("created_at", DateTime),
    )

    Table(
        "lab_host_events",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("host_id", Integer, nullable=False),
        Column("kind", String(64), nullable=False),
        Column("timestamp_utc", DateTime, nullable=False),
        Column("payload", Text),
        Column("created_at", DateTime),
    )

    Table(
        "lab_reservations",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("transaction_hash", String(66), nullable=False, unique=True),
        Column("user_id", Integer, nullable=False),
        Column("wallet_address", String(42), nullable=False),
        Column("lab_id", String(128), nullable=False),
        Column("start_time", DateTime, nullable=False),
        Column("end_time", DateTime, nullable=False),
        Column("status", String(32), nullable=False),
        Column("created_at", DateTime),
        Column("updated_at", DateTime),
    )

    Table(
        "reservation_operations",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("reservation_id", String(128), nullable=False),
        Column("lab_id", String(128)),
        Column("host", String(128), nullable=False),
        Column("action", String(32), nullable=False),
        Column("status", String(32), nullable=False),
        Column("success", Boolean, nullable=False, default=False),
        Column("response_code", Integer),
        Column("duration_ms", Integer),
        Column("payload", Text),
        Column("message", Text),
        Column("created_at", DateTime),
    )

    metadata.create_all(engine)
    original_engine = worker.DB_ENGINE
    worker.DB_ENGINE = engine
    try:
        yield engine
    finally:
        worker.DB_ENGINE = original_engine
