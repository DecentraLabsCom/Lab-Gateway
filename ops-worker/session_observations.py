"""Durable session observations and Guacamole token revocation integration."""

import base64
import hashlib
import hmac
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def default_retry_delay_seconds(attempts: int) -> int:
    """Bound exponential retry backoff for durable observation delivery."""
    return min(300, 5 * (2 ** min(max(0, attempts - 1), 6)))


class SessionObservations:
    """Coordinate the observation and revocation outboxes through explicit ports.

    The service owns persistence and remote integration policy.  Flask, module
    globals and the concrete HTTP/SQL clients stay in the composition root.
    """

    def __init__(
        self,
        *,
        db_engine: Any,
        guacamole_db_engine: Any,
        encrypt_secret: Callable[[str], str],
        decrypt_secret: Callable[[str], str],
        http_get: Callable[..., Any],
        http_post: Callable[..., Any],
        http_delete: Callable[..., Any],
        sql_text: Callable[[str], Any],
        integrity_error_type: type[BaseException],
        enqueue_session_observation: Callable[[Mapping[str, Any]], bool],
        retry_delay: Callable[[int], int],
        to_utc: Callable[[Any], Optional[datetime]],
        now: Callable[[], datetime],
        current_epoch: Callable[[], float],
        config: Mapping[str, Any],
        logger: Any,
        random_bytes: Callable[[int], bytes] = os.urandom,
    ):
        self.db_engine = db_engine
        self.guacamole_db_engine = guacamole_db_engine
        self.encrypt_secret = encrypt_secret
        self.decrypt_secret = decrypt_secret
        self.http_get = http_get
        self.http_post = http_post
        self.http_delete = http_delete
        self.sql_text = sql_text
        self.integrity_error_type = integrity_error_type
        self.enqueue_session_observation_callback = enqueue_session_observation
        self.retry_delay = retry_delay
        self.to_utc = to_utc
        self.now = now
        self.current_epoch = current_epoch
        self.config = dict(config)
        self.logger = logger
        self.random_bytes = random_bytes

    def enqueue_guacamole_token_revocation(self, payload: Mapping[str, Any]) -> bool:
        if not self.db_engine:
            return False
        required = ("authToken", "username", "reservationKey", "jwtJti", "gatewayId", "expiresAt")
        if any(not str(payload.get(field) or "").strip() for field in required):
            return False
        token = str(payload["authToken"]).strip()
        if len(token) > 512:
            return False
        try:
            expires_at = datetime.fromtimestamp(
                int(payload["expiresAt"]),
                tz=timezone.utc,
            ).replace(tzinfo=None)
            ciphertext = self.encrypt_secret(token)
        except (TypeError, ValueError, OverflowError):
            return False
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        values = {
            "token_hash": token_hash,
            "token_ciphertext": ciphertext,
            "username": str(payload["username"]).strip().lower(),
            "reservation_key": str(payload["reservationKey"]).strip(),
            "jwt_jti": str(payload["jwtJti"]).strip(),
            "gateway_id": str(payload["gatewayId"]).strip(),
            "expires_at": expires_at,
        }
        try:
            with self.db_engine.begin() as conn:
                conn.execute(
                    self.sql_text(
                        """
                        INSERT INTO guacamole_token_revocation_queue (
                            token_hash, token_ciphertext, token_validated_at, username, reservation_key,
                            jwt_jti, gateway_id, expires_at, status, next_attempt_at
                        ) VALUES (
                            :token_hash, :token_ciphertext, CURRENT_TIMESTAMP, :username, :reservation_key,
                            :jwt_jti, :gateway_id, :expires_at, 'PENDING', CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    values,
                )
            return True
        except self.integrity_error_type:
            try:
                with self.db_engine.begin() as conn:
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE guacamole_token_revocation_queue
                            SET token_ciphertext = :token_ciphertext,
                                token_validated_at = COALESCE(token_validated_at, CURRENT_TIMESTAMP),
                                username = :username,
                                reservation_key = :reservation_key,
                                jwt_jti = :jwt_jti,
                                gateway_id = :gateway_id,
                                expires_at = :expires_at,
                                attempts = CASE WHEN status = 'FAILED' THEN 0 ELSE attempts END,
                                next_attempt_at = CASE
                                    WHEN status = 'FAILED' THEN CURRENT_TIMESTAMP
                                    ELSE next_attempt_at
                                END,
                                last_error = CASE WHEN status = 'FAILED' THEN NULL ELSE last_error END,
                                status = CASE WHEN status = 'FAILED' THEN 'RETRY' ELSE status END,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE token_hash = :token_hash AND status != 'REVOKED'
                            """
                        ),
                        values,
                    )
                return True
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Guacamole revocation duplicate recovery failed: %s", exc)
                return False
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Guacamole revocation ingest failed: %s", exc)
            return False

    def guacamole_admin_session(self) -> Optional[Tuple[str, str]]:
        admin_user = str(self.config.get("guac_admin_user") or "")
        admin_pass = str(self.config.get("guac_admin_pass") or "")
        if not admin_user or not admin_pass:
            return None
        api_url = str(self.config.get("guac_api_url") or "").rstrip("/")
        response = self.http_post(
            f"{api_url}/tokens",
            data={"username": admin_user, "password": admin_pass},
            timeout=5,
        )
        if response.status_code != 200:
            return None
        body = response.json()
        token = str(body.get("authToken") or "").strip()
        data_source = str(body.get("dataSource") or "mysql").strip()
        return (token, data_source) if token else None

    def guacamole_connection_history_observed(
        self,
        row: Mapping[str, Any],
    ) -> Optional[datetime]:
        """Return the real Guacamole connection start for this token user."""
        if not self.guacamole_db_engine:
            return None
        username = str(row.get("username") or "").strip().lower()
        if not username:
            return None
        issued_at = self.to_utc(row.get("token_validated_at") or row.get("created_at"))
        expires_at = self.to_utc(row.get("expires_at"))
        if not issued_at or not expires_at:
            return None
        window_start = issued_at - timedelta(
            seconds=max(0, int(self.config.get("guacamole_history_lookback_seconds", 30)))
        )
        try:
            with self.guacamole_db_engine.connect() as conn:
                found = conn.execute(
                    self.sql_text(
                        """
                        SELECT start_date
                        FROM guacamole_connection_history
                        WHERE LOWER(username) = :username
                          AND start_date >= :window_start
                          AND start_date <= :expires_at
                          AND (end_date IS NULL OR end_date >= :window_start)
                        ORDER BY start_date ASC
                        LIMIT 1
                        """
                    ),
                    {
                        "username": username,
                        "window_start": window_start.replace(tzinfo=None),
                        "expires_at": expires_at.replace(tzinfo=None),
                    },
                ).first()
                return self.to_utc(found[0]) if found is not None else None
        except Exception as exc:  # pylint: disable=broad-except
            # Older Guacamole schemas may not expose connection history.  The
            # activeConnections path remains a valid fallback in that case.
            self.logger.debug("Unable to query Guacamole connection history: %s", exc)
            return None

    def reconcile_guacamole_observations(self, admin_token: str, data_source: str) -> None:
        if not self.db_engine:
            return
        api_url = str(self.config.get("guac_api_url") or "").rstrip("/")
        response = self.http_get(
            f"{api_url}/session/data/{self._quote(data_source)}/activeConnections",
            params={"token": admin_token},
            timeout=5,
        )
        if response.status_code != 200:
            return
        active_users = {
            str(connection.get("username") or "").strip().lower()
            for connection in (response.json() or {}).values()
            if isinstance(connection, dict)
        }
        retention = max(
            0,
            int(self.config.get("guacamole_history_reconciliation_retention_seconds", 300)),
        )
        evidence_cutoff = self.now().replace(tzinfo=None) - timedelta(seconds=retention)
        with self.db_engine.begin() as conn:
            rows = conn.execute(
                self.sql_text(
                    """
                    SELECT token_hash, token_ciphertext, token_validated_at, reservation_key,
                           jwt_jti, gateway_id, username, created_at, expires_at, status
                    FROM guacamole_token_revocation_queue
                    WHERE status IN ('PENDING', 'RETRY', 'REVOKED')
                      AND observed_at IS NULL
                      AND expires_at > :evidence_cutoff
                    ORDER BY created_at ASC
                    LIMIT 100
                    """
                ),
                {"evidence_cutoff": evidence_cutoff},
            ).mappings().all()
        for row in rows:
            history_row: Dict[str, Any] = {str(key): value for key, value in row.items()}
            history_started_at = self.guacamole_connection_history_observed(history_row)
            active_observed = str(row["username"]).lower() in active_users
            if not active_observed and history_started_at is None:
                continue
            historical_after_revocation = (
                str(row.get("status") or "").upper() == "REVOKED"
                and history_started_at is not None
                and row.get("token_validated_at") is not None
            )
            if not historical_after_revocation:
                try:
                    user_token = self.decrypt_secret(str(row["token_ciphertext"]))
                    token_response = self.http_get(
                        f"{api_url}/session/data/{self._quote(data_source)}",
                        params={"token": user_token},
                        timeout=5,
                    )
                    # Before revocation, the exact token must still be accepted.
                    # After revocation, a pre-revocation validation marker plus a
                    # matching historical connection is the durable proof.
                    if token_response.status_code != 200:
                        continue
                except Exception as exc:  # pylint: disable=broad-except
                    self.logger.warning("Unable to validate Guacamole token: %s", exc)
                    continue
            observed_at = history_started_at or self.now()
            accepted = self.enqueue_session_observation_callback(
                {
                    "dedupKey": row["token_hash"],
                    "reservationKey": row["reservation_key"],
                    "jwtJti": row["jwt_jti"],
                    "sessionId": f"guac:{row['token_hash']}",
                    "gatewayId": row["gateway_id"],
                    "accessType": "guacamole",
                    "observedAt": int(observed_at.timestamp()),
                }
            )
            if accepted:
                with self.db_engine.begin() as conn:
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE guacamole_token_revocation_queue
                            SET observed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                            WHERE token_hash = :token_hash AND observed_at IS NULL
                            """
                        ),
                        {"token_hash": row["token_hash"]},
                    )

    def process_guacamole_token_revocations(self) -> int:
        if not self.db_engine:
            return 0
        session = self.guacamole_admin_session()
        if not session:
            self.logger.warning("Guacamole token revocation deferred: admin session unavailable")
            return 0
        admin_token, data_source = session
        try:
            self.reconcile_guacamole_observations(admin_token, data_source)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Guacamole session observation reconciliation failed: %s", exc)
        with self.db_engine.begin() as conn:
            rows = conn.execute(
                self.sql_text(
                    """
                    SELECT token_hash, token_ciphertext, attempts
                    FROM guacamole_token_revocation_queue
                    WHERE status IN ('PENDING', 'RETRY')
                      AND expires_at <= CURRENT_TIMESTAMP
                      AND next_attempt_at <= CURRENT_TIMESTAMP
                    ORDER BY expires_at ASC
                    LIMIT 100
                    """
                )
            ).mappings().all()
        max_attempts = max(1, int(self.config.get("guac_token_revocation_max_attempts", 20)))
        revoked = 0
        for row in rows:
            attempts = int(row["attempts"] or 0) + 1
            try:
                user_token = self.decrypt_secret(str(row["token_ciphertext"]))
                api_url = str(self.config.get("guac_api_url") or "").rstrip("/")
                response = self.http_delete(
                    f"{api_url}/tokens/{self._quote(user_token)}",
                    params={"token": admin_token},
                    timeout=5,
                )
                if response.status_code not in (204, 404):
                    raise RuntimeError(f"Guacamole token delete returned {response.status_code}")
                with self.db_engine.begin() as conn:
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE guacamole_token_revocation_queue
                            SET status = 'REVOKED', attempts = :attempts,
                                revoked_at = CURRENT_TIMESTAMP, last_error = NULL,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE token_hash = :token_hash
                            """
                        ),
                        {"token_hash": row["token_hash"], "attempts": attempts},
                    )
                revoked += 1
            except Exception as exc:  # pylint: disable=broad-except
                status = "FAILED" if attempts >= max_attempts else "RETRY"
                self.logger.warning(
                    "Guacamole token revocation failed for %s: %s",
                    row["token_hash"],
                    exc,
                )
                next_attempt = self.now() + timedelta(seconds=self.retry_delay(attempts))
                with self.db_engine.begin() as conn:
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE guacamole_token_revocation_queue
                            SET status = :status, attempts = :attempts,
                                next_attempt_at = :next_attempt_at, last_error = :last_error,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE token_hash = :token_hash
                            """
                        ),
                        {
                            "status": status,
                            "attempts": attempts,
                            "next_attempt_at": next_attempt,
                            "last_error": "Guacamole token revocation failed",
                            "token_hash": row["token_hash"],
                        },
                    )
        return revoked

    def enqueue_session_observation(self, payload: Mapping[str, Any]) -> bool:
        """Persist evidence produced after a runtime confirms an active session."""
        if not self.db_engine:
            return False
        required_fields = (
            "dedupKey",
            "reservationKey",
            "jwtJti",
            "sessionId",
            "gatewayId",
            "accessType",
            "observedAt",
        )
        if any(not str(payload.get(field) or "").strip() for field in required_fields):
            return False
        try:
            observed_at = datetime.fromtimestamp(
                int(payload["observedAt"]),
                tz=timezone.utc,
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            return False
        try:
            with self.db_engine.begin() as conn:
                conn.execute(
                    self.sql_text(
                        """
                        INSERT INTO gateway_session_observation_outbox (
                            dedup_key, reservation_key, jwt_jti, session_id, gateway_id,
                            access_type, observed_at, status, next_attempt_at
                        ) VALUES (
                            :dedup_key, :reservation_key, :jwt_jti, :session_id, :gateway_id,
                            :access_type, :observed_at, 'PENDING', CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "dedup_key": str(payload["dedupKey"]).strip(),
                        "reservation_key": str(payload["reservationKey"]).strip(),
                        "jwt_jti": str(payload["jwtJti"]).strip(),
                        "session_id": str(payload["sessionId"]).strip(),
                        "gateway_id": str(payload["gatewayId"]).strip(),
                        "access_type": str(payload["accessType"]).strip().lower(),
                        "observed_at": observed_at,
                    },
                )
            return True
        except self.integrity_error_type:
            # A repeated WebSocket observation is idempotent. A terminal delivery
            # is reopened only when the trusted gateway observes the same session again.
            try:
                with self.db_engine.begin() as conn:
                    conn.execute(
                        self.sql_text(
                            """
                            UPDATE gateway_session_observation_outbox
                            SET attempts = CASE WHEN status = 'FAILED' THEN 0 ELSE attempts END,
                                next_attempt_at = CASE
                                    WHEN status IN ('FAILED', 'RETRY') THEN CURRENT_TIMESTAMP
                                    ELSE next_attempt_at
                                END,
                                locked_at = CASE WHEN status = 'FAILED' THEN NULL ELSE locked_at END,
                                last_error = CASE WHEN status = 'FAILED' THEN NULL ELSE last_error END,
                                status = CASE WHEN status = 'FAILED' THEN 'RETRY' ELSE status END,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE dedup_key = :dedup_key
                            """
                        ),
                        {"dedup_key": str(payload["dedupKey"]).strip()},
                    )
                return True
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Session observation duplicate recovery failed: %s", exc)
                return False
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Session observation outbox ingest failed: %s", exc)
            return False

    def claim_session_observation_outbox_rows(self) -> List[Dict[str, Any]]:
        if not self.db_engine:
            return []
        cutoff = self.now() - timedelta(seconds=60)
        batch_size = max(1, int(self.config.get("session_observation_outbox_batch_size", 20)))
        try:
            with self.db_engine.begin() as conn:
                conn.execute(
                    self.sql_text(
                        """
                        UPDATE gateway_session_observation_outbox
                        SET status = 'RETRY', next_attempt_at = CURRENT_TIMESTAMP,
                            locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE status = 'SENDING' AND locked_at < :cutoff
                        """
                    ),
                    {"cutoff": cutoff},
                )
                rows = conn.execute(
                    self.sql_text(
                        """
                        SELECT id, reservation_key, jwt_jti, session_id, gateway_id,
                               access_type, observed_at, attempts
                        FROM gateway_session_observation_outbox
                        WHERE status IN ('PENDING', 'RETRY')
                          AND next_attempt_at <= CURRENT_TIMESTAMP
                        ORDER BY next_attempt_at ASC, id ASC
                        LIMIT :limit
                        """
                    ),
                    {"limit": batch_size},
                ).mappings().all()
                claimed = []
                for row in rows:
                    updated = conn.execute(
                        self.sql_text(
                            """
                            UPDATE gateway_session_observation_outbox
                            SET status = 'SENDING', locked_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id AND status IN ('PENDING', 'RETRY')
                            """
                        ),
                        {"id": row["id"]},
                    ).rowcount
                    if updated == 1:
                        claimed.append(dict(row))
                return claimed
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Session observation outbox claim failed: %s", exc)
            return []

    def mark_session_observation_delivered(self, record_id: int) -> None:
        if not self.db_engine:
            return
        with self.db_engine.begin() as conn:
            conn.execute(
                self.sql_text(
                    """
                    UPDATE gateway_session_observation_outbox
                    SET status = 'SENT', delivered_at = CURRENT_TIMESTAMP,
                        locked_at = NULL, last_error = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND status = 'SENDING'
                    """
                ),
                {"id": record_id},
            )

    def mark_session_observation_failure(
        self,
        record: Mapping[str, Any],
        error: str,
    ) -> None:
        if not self.db_engine:
            return
        attempts = int(record.get("attempts") or 0) + 1
        max_attempts = max(1, int(self.config.get("session_observation_outbox_max_attempts", 20)))
        status = "FAILED" if attempts >= max_attempts else "RETRY"
        next_attempt = self.now() + timedelta(seconds=self.retry_delay(attempts))
        with self.db_engine.begin() as conn:
            conn.execute(
                self.sql_text(
                    """
                    UPDATE gateway_session_observation_outbox
                    SET status = :status, attempts = :attempts,
                        next_attempt_at = :next_attempt_at, locked_at = NULL,
                        last_error = :last_error, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND status = 'SENDING'
                    """
                ),
                {
                    "id": record["id"],
                    "status": status,
                    "attempts": attempts,
                    "next_attempt_at": next_attempt,
                    "last_error": str(error)[:1024],
                },
            )

    def session_observed_epoch(self, value: Any) -> int:
        if isinstance(value, datetime):
            return int((value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp())
        parsed = self.to_utc(value)
        if parsed:
            return int(parsed.timestamp())
        return int(self.current_epoch())

    def base64url_json(self, value: Mapping[str, Any]) -> str:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")

    def session_observer_authorization(self) -> str:
        """Create a short-lived JWT scoped only to session-observation submission."""
        gateway_id = str(self.config.get("session_observer_gateway_id") or "")
        signing_secret = str(self.config.get("session_observer_signing_secret") or "")
        if not gateway_id or not signing_secret:
            raise RuntimeError("session observer gateway credentials are not configured")
        padding = "=" * (-len(signing_secret) % 4)
        key = base64.urlsafe_b64decode(signing_secret + padding)
        if len(key) < 32:
            raise RuntimeError("session observer signing secret must contain at least 32 bytes")
        now = int(self.current_epoch())
        header = self.base64url_json({"alg": "HS256", "typ": "JWT"})
        payload = self.base64url_json(
            {
                "iss": gateway_id,
                "sub": gateway_id,
                "aud": "session-observation",
                "scope": "session-observation:submit",
                "iat": now,
                "exp": now + 60,
                "jti": base64.urlsafe_b64encode(self.random_bytes(18)).rstrip(b"=").decode("ascii"),
            }
        )
        signing_input = f"{header}.{payload}"
        signature = base64.urlsafe_b64encode(
            hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        return f"Bearer {signing_input}.{signature}"

    def deliver_session_observation_outbox(self) -> int:
        """Deliver durable runtime-confirmed observations to blockchain-services."""
        if not self.config.get("session_observation_outbox_enabled") or not self.db_engine:
            return 0
        access_audit_url = str(self.config.get("access_audit_url") or "").strip()
        if not access_audit_url:
            self.logger.error(
                "Session observation outbox is pending: ACCESS_AUDIT_URL must target the issuing Full gateway"
            )
            return 0
        gateway_id = str(self.config.get("session_observer_gateway_id") or "")
        signing_secret = str(self.config.get("session_observer_signing_secret") or "")
        if not gateway_id or not signing_secret:
            self.logger.error("Session observation outbox is pending: session observer credentials are not configured")
            return 0

        timeout = max(
            1,
            int(self.config.get("session_observation_outbox_request_timeout_seconds", 5)),
        )
        delivered = 0
        for record in self.claim_session_observation_outbox_rows():
            try:
                authorization = self.session_observer_authorization()
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Observer authorization failed: %s", exc)
                self.mark_session_observation_failure(record, "Observer authorization failed")
                continue
            reported_at = int(self.current_epoch())
            payload = {
                "reservationKey": record["reservation_key"],
                "jwtJti": record["jwt_jti"],
                "sessionId": record["session_id"],
                "gatewayId": gateway_id,
                "accessType": record["access_type"],
                "observedAt": self.session_observed_epoch(record["observed_at"]),
                "reportedAt": reported_at,
            }
            try:
                response = self.http_post(
                    access_audit_url,
                    json=payload,
                    headers={"Authorization": authorization},
                    timeout=timeout,
                )
                body = response.json() if response.content else {}
                if 200 <= response.status_code < 300 and body.get("recorded") is True:
                    self.mark_session_observation_delivered(record["id"])
                    delivered += 1
                else:
                    self.mark_session_observation_failure(
                        record,
                        f"audit endpoint status={response.status_code} recorded={body.get('recorded')!r}",
                    )
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Audit delivery failed: %s", exc)
                self.mark_session_observation_failure(record, "Audit delivery failed")
        return delivered

    @staticmethod
    def _quote(value: Any) -> str:
        from urllib.parse import quote

        return quote(str(value), safe="")


__all__ = ["SessionObservations"]
