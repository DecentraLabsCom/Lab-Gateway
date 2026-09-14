"""Explicit maintenance command for Guacamole session observations.

This command deliberately composes the observation runtime without importing
the Flask worker entrypoint.  It is used by operational integration checks and
can also be invoked manually inside the ops-worker image.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import requests
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError

from datetime_values import to_utc as normalize_to_utc
from guacamole_dsn import build_guacamole_dsn
from input_values import parse_recipients
from ops_dsn import build_ops_dsn
from runtime_config import is_lite_gateway, load_runtime_paths, load_runtime_policy
from runtime_values import HTTP_HEADER_NAME_RE
from secret_values import env_or_secret_file
from session_observation_runtime import create_session_observation_runtime
from session_observations import SessionObservations, default_retry_delay_seconds
from winrm_credential_store import decrypt_secret, encrypt_secret, load_fernet


class _StaticResponse:
    def __init__(self, payload: Mapping[str, Any], status_code: int = 200):
        self._payload = dict(payload)
        self.status_code = status_code

    def json(self) -> Mapping[str, Any]:
        return self._payload


def _engine(dsn: Optional[str]) -> Any:
    return create_engine(dsn, pool_pre_ping=True) if dsn else None


def build_runtime(
    active_connections: Optional[Mapping[str, Any]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Any:
    """Compose a session-observation runtime from process configuration."""
    env = dict(environ or os.environ)
    secret_loader = lambda name: env_or_secret_file(name, logger=logging)
    paths = load_runtime_paths(
        environ=env,
        secret_loader=secret_loader,
        default_config_path=os.path.join(os.path.dirname(__file__), "hosts.json"),
    )
    policy = load_runtime_policy(
        environ=env,
        secret_loader=secret_loader,
        parse_recipients=parse_recipients,
        http_header_pattern=HTTP_HEADER_NAME_RE,
        is_lite=lambda: is_lite_gateway(env),
        log_error=logging.error,
    )
    ops_dsn = build_ops_dsn(
        paths.mysql_dsn,
        paths.ops_mysql_user,
        paths.ops_mysql_password,
        paths.ops_mysql_database,
        paths.mysql_hostname,
        paths.mysql_port,
        create_url=URL.create,
    )
    guacamole_dsn = build_guacamole_dsn(
        paths.guacamole_mysql_dsn,
        paths.guacamole_mysql_user,
        paths.guacamole_mysql_password,
        paths.guacamole_mysql_database,
        paths.mysql_dsn,
        paths.mysql_hostname,
        paths.mysql_port,
        create_url=URL.create,
        parse_url=make_url,
        logger=logging,
    )
    fernet_cache: dict[str, Optional[Fernet]] = {"value": None}

    def load_runtime_fernet() -> Fernet:
        value = load_fernet(
            fernet_cache["value"],
            read_secret=secret_loader,
            fernet_factory=Fernet,
        )
        fernet_cache["value"] = value
        return value

    providers: dict[str, Any] = {
        "SessionObservations": SessionObservations,
        "DB_ENGINE": _engine(ops_dsn),
        "GUACAMOLE_DB_ENGINE": _engine(guacamole_dsn),
        "requests": requests,
        "text": text,
        "IntegrityError": IntegrityError,
        "_encrypt_secret_impl": encrypt_secret,
        "_decrypt_secret_impl": decrypt_secret,
        "_load_fernet": load_runtime_fernet,
        "_encrypt_runtime_secret": lambda value: encrypt_secret(
            value,
            load_fernet=providers["_load_fernet"],
        ),
        "_decrypt_runtime_secret": lambda value: decrypt_secret(
            value,
            load_fernet=providers["_load_fernet"],
        ),
        "session_observation_retry_delay_seconds": default_retry_delay_seconds,
        "to_utc": lambda value: normalize_to_utc(
            value,
            parse_datetime=datetime.fromisoformat,
            utc_timezone=timezone.utc,
        ),
        "datetime": datetime,
        "timezone": timezone,
        "time": time,
        "logging": logging,
        "ACCESS_AUDIT_URL": policy.access_audit_url,
        "SESSION_OBSERVER_GATEWAY_ID": policy.session_observer_gateway_id,
        "SESSION_OBSERVER_SIGNING_SECRET": policy.session_observer_signing_secret,
        "SESSION_OBSERVATION_OUTBOX_ENABLED": policy.session_observation_outbox_enabled,
        "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE": policy.session_observation_outbox_batch_size,
        "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS": policy.session_observation_outbox_max_attempts,
        "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS": policy.session_observation_outbox_request_timeout_seconds,
        "GUAC_ADMIN_USER": policy.guac_admin_user,
        "GUAC_ADMIN_PASS": policy.guac_admin_pass,
        "GUAC_API_URL": policy.guac_api_url,
        "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS": policy.guac_token_revocation_max_attempts,
        "GUACAMOLE_HISTORY_LOOKBACK_SECONDS": policy.guacamole_history_lookback_seconds,
        "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS": policy.guacamole_history_reconciliation_retention_seconds,
    }
    service_holder: dict[str, SessionObservations] = {}
    providers["enqueue_session_observation"] = lambda payload: service_holder[
        "service"
    ].enqueue_session_observation(payload)
    providers["_session_observations_service"] = lambda: service_holder["service"]

    if active_connections is not None:
        providers["requests"] = type(
            "_RequestsAdapter",
            (),
            {
                "get": staticmethod(
                    lambda url, *args, **kwargs: (
                        _StaticResponse(active_connections)
                        if str(url).rstrip("/").endswith("/activeConnections")
                        else requests.get(url, *args, **kwargs)
                    )
                ),
                "post": staticmethod(requests.post),
                "delete": staticmethod(requests.delete),
            },
        )

    runtime = create_session_observation_runtime(providers)
    service_holder["service"] = runtime.create_service()
    return runtime


def run_reconciliation(
    admin_token: str,
    data_source: str,
    *,
    active_connections: Optional[Mapping[str, Any]] = None,
    runtime_factory: Callable[[Optional[Mapping[str, Any]]], Any] = build_runtime,
) -> None:
    """Run reconciliation through an explicitly supplied runtime boundary."""
    runtime_factory(active_connections).reconcile_guacamole_observations(
        admin_token,
        data_source,
    )


def _parse_active_connections(value: Optional[str]) -> Optional[Mapping[str, Any]]:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("active connections must be a JSON object")
    return parsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-token", required=True)
    parser.add_argument("--data-source", default="mysql")
    parser.add_argument(
        "--active-connections-json",
        help="Use this JSON object instead of querying Guacamole activeConnections.",
    )
    args = parser.parse_args(argv)
    try:
        active_connections = _parse_active_connections(args.active_connections_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    run_reconciliation(
        args.admin_token,
        args.data_source,
        active_connections=active_connections,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_runtime", "run_reconciliation", "main"]
