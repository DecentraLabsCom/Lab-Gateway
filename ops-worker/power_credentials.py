#!/usr/bin/env python3
"""Provision provider-local power credentials without printing secret values."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from power.credentials import PowerCredentialError, PowerCredentialStore


def _read_payload() -> Mapping[str, Any]:
    try:
        payload = json.loads(sys.stdin.read())
    except (OSError, json.JSONDecodeError) as exc:
        raise PowerCredentialError("credential payload must be valid JSON from stdin") from exc
    if not isinstance(payload, Mapping) or not payload:
        raise PowerCredentialError("credential payload must be a non-empty JSON object")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    set_command = commands.add_parser("set", help="encrypt one credential from JSON on stdin")
    set_command.add_argument("--ref", required=True, help="credentialRef to use in the power catalog")
    set_command.add_argument("--type", required=True, help="provider credential type, for example snmpv2c")
    set_command.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing credential with the same reference",
    )
    commands.add_parser("list", help="list references and types, never secret payloads")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        store = PowerCredentialStore.from_environment()
        if args.command == "list":
            result = store.list()
        else:
            result = store.put(
                args.ref,
                args.type,
                _read_payload(),
                overwrite=args.overwrite,
            )
    except PowerCredentialError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
