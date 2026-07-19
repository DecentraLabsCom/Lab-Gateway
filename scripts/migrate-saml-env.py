#!/usr/bin/env python3
"""Merge newly introduced SAML settings into an existing backend .env.

The setup scripts intentionally preserve an existing environment file. This
small migration keeps that behavior while adding only missing metadata settings
and merging new issuer-specific overrides without replacing operator values.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ASSIGNMENT = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
MERGE_MAP_KEYS = ("SAML_IDP_METADATA_OVERRIDE", "SAML_IDP_METADATA_TLS_PROFILE")
COPY_KEYS = ("SAML_METADATA_HEALTH_CACHE_MS",)


def parse_assignments(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match:
            values[match.group("key")] = match.group("value")
    return values


def replace_assignment(lines: list[str], key: str, value: str) -> None:
    for index, line in enumerate(lines):
        if ASSIGNMENT.match(line.strip()) and line.strip().split("=", 1)[0] == key:
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"{key}={value}{newline}"
            return
    lines.append(f"{key}={value}\n")


def merge_map(existing: str, template: str, key: str) -> str:
    try:
        existing_map = json.loads(existing) if existing.strip() else {}
        template_map = json.loads(template) if template.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} is not valid JSON: {exc}") from exc
    if not isinstance(existing_map, dict) or not isinstance(template_map, dict):
        raise ValueError(f"{key} must be a JSON object")
    merged = dict(template_map)
    merged.update(existing_map)
    return json.dumps(merged, separators=(",", ":"), ensure_ascii=False)


def migrate(env_path: Path, template_path: Path) -> bool:
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    template_text = template_path.read_text(encoding="utf-8")
    env_values = parse_assignments(env_text)
    template_values = parse_assignments(template_text)
    lines = env_text.splitlines(keepends=True)
    changed = False

    for key in MERGE_MAP_KEYS:
        template_value = template_values.get(key)
        if template_value is None:
            continue
        existing_value = env_values.get(key)
        if existing_value is None:
            replace_assignment(lines, key, template_value)
            changed = True
            continue
        merged = merge_map(existing_value, template_value, key)
        if merged != existing_value:
            replace_assignment(lines, key, merged)
            changed = True

    for key in COPY_KEYS:
        if key not in env_values and key in template_values:
            replace_assignment(lines, key, template_values[key])
            changed = True

    if changed:
        env_path.write_text("".join(lines), encoding="utf-8", newline="")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    args = parser.parse_args()
    try:
        changed = migrate(args.env, args.template)
    except (OSError, ValueError) as exc:
        print(f"SAML environment migration failed: {exc}")
        return 1
    print("SAML environment migration applied." if changed else "SAML environment already current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
