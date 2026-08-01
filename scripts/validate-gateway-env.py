#!/usr/bin/env python3
"""Validate gateway credential-map configuration before Compose starts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PLACEHOLDER_VALUES = {"", "change_me", "changeme"}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_map(values: dict[str, str], key: str) -> dict[str, str]:
    raw = values.get(key, "")
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{key} must be a JSON object keyed by gateway ID") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(map_key, str)
        or not map_key.strip()
        or not isinstance(map_value, str)
        or not map_value.strip()
        for map_key, map_value in parsed.items()
    ):
        raise SystemExit(f"{key} must be a JSON object keyed by gateway ID")
    return {map_key.strip().lower(): map_value for map_key, map_value in parsed.items()}


def validate(path: Path) -> None:
    values = read_env(path)
    redeemers = parse_map(values, "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON")
    observers = parse_map(values, "SESSION_OBSERVER_CREDENTIALS_JSON")

    # Lite gateways do not run the embedded issuer. Their imported trust bundle
    # is validated by setup separately, but the local maps still must not carry
    # a malformed value that would break a later mode switch.
    issuer = values.get("ISSUER", "").strip()
    if issuer:
        return

    gateway_id = values.get("SERVER_NAME", "").strip().lower().rstrip(".")
    if not gateway_id:
        raise SystemExit("SERVER_NAME is required in Full mode")

    redeemer = values.get("AUTH_ACCESS_CODE_REDEEMER_TOKEN", "").strip()
    if redeemer.lower() in PLACEHOLDER_VALUES:
        raise SystemExit("AUTH_ACCESS_CODE_REDEEMER_TOKEN must be configured in Full mode")
    if redeemers.get(gateway_id) != redeemer:
        raise SystemExit(
            "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON must contain the Full gateway "
            "SERVER_NAME mapped to AUTH_ACCESS_CODE_REDEEMER_TOKEN"
        )

    observer_id = values.get("SESSION_OBSERVER_GATEWAY_ID", "").strip().lower().rstrip(".")
    if observer_id != gateway_id:
        raise SystemExit("SESSION_OBSERVER_GATEWAY_ID must match SERVER_NAME in Full mode")
    observer_secret = values.get("SESSION_OBSERVER_SIGNING_SECRET", "").strip()
    if observer_secret.lower() in PLACEHOLDER_VALUES:
        raise SystemExit("SESSION_OBSERVER_SIGNING_SECRET must be configured in Full mode")
    if observers.get(gateway_id) != observer_secret:
        raise SystemExit(
            "SESSION_OBSERVER_CREDENTIALS_JSON must contain the Full gateway "
            "SERVER_NAME mapped to SESSION_OBSERVER_SIGNING_SECRET"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, type=Path)
    args = parser.parse_args()
    validate(args.env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
