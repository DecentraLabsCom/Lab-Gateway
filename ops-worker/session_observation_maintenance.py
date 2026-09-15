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
from session_observation_context import SessionObservationContext
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

    ops_engine = _engine(ops_dsn)
    guacamole_engine = _engine(guacamole_dsn)

    def close_engines() -> None:
        if ops_engine is not None:
            try:
                ops_engine.dispose()
            finally:
                if guacamole_engine is not None:
                    guacamole_engine.dispose()
        elif guacamole_engine is not None:
            guacamole_engine.dispose()

    http_get = requests.get
    http_post = requests.post
    http_delete = requests.delete
    service_holder: dict[str, SessionObservations] = {}

    if active_connections is not None:
        http_get = lambda url, *args, **kwargs: (
            _StaticResponse(active_connections)
            if str(url).rstrip("/").endswith("/activeConnections")
            else requests.get(url, *args, **kwargs)
        )
        http_post = requests.post
        http_delete = requests.delete

    context = SessionObservationContext(
        get_session_observations_factory=lambda: SessionObservations,
        get_db_engine=lambda: ops_engine,
        get_guacamole_db_engine=lambda: guacamole_engine,
        get_encrypt_secret=lambda: lambda value: encrypt_secret(
            value,
            load_fernet=load_runtime_fernet,
        ),
        get_decrypt_secret=lambda: lambda value: decrypt_secret(
            value,
            load_fernet=load_runtime_fernet,
        ),
        get_http_get=lambda: http_get,
        get_http_post=lambda: http_post,
        get_http_delete=lambda: http_delete,
        get_sql_text=lambda: text,
        get_integrity_error_type=lambda: IntegrityError,
        get_enqueue_session_observation=lambda: (
            lambda payload: service_holder["service"].enqueue_session_observation(payload)
        ),
        get_retry_delay=lambda: default_retry_delay_seconds,
        get_to_utc=lambda: lambda value: normalize_to_utc(
            value,
            parse_datetime=datetime.fromisoformat,
            utc_timezone=timezone.utc,
        ),
        get_now=lambda: lambda: datetime.now(timezone.utc),
        get_current_epoch=lambda: time.time,
        get_config=lambda: {
            "access_audit_url": policy.access_audit_url,
            "session_observer_gateway_id": policy.session_observer_gateway_id,
            "session_observer_signing_secret": policy.session_observer_signing_secret,
            "session_observation_outbox_enabled": policy.session_observation_outbox_enabled,
            "session_observation_outbox_batch_size": policy.session_observation_outbox_batch_size,
            "session_observation_outbox_max_attempts": policy.session_observation_outbox_max_attempts,
            "session_observation_outbox_request_timeout_seconds": policy.session_observation_outbox_request_timeout_seconds,
            "guac_admin_user": policy.guac_admin_user,
            "guac_admin_pass": policy.guac_admin_pass,
            "guac_api_url": policy.guac_api_url,
            "guac_token_revocation_max_attempts": policy.guac_token_revocation_max_attempts,
            "guacamole_history_lookback_seconds": policy.guacamole_history_lookback_seconds,
            "guacamole_history_reconciliation_retention_seconds": policy.guacamole_history_reconciliation_retention_seconds,
        },
        get_logger=lambda: logging,
        get_service=lambda: service_holder["service"],
    )

    runtime = create_session_observation_runtime(context, close=close_engines)
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
    runtime = runtime_factory(active_connections)
    try:
        runtime.reconcile_guacamole_observations(
            admin_token,
            data_source,
        )
    finally:
        runtime.close()


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
