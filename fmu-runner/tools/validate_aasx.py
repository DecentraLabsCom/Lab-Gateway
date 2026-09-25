"""Strictly validate an AASX package with the Eclipse BaSyx Python SDK.

This is a development tool. Install ``requirements-dev.txt`` first and run:

    python tools/validate_aasx.py path/to/package.aasx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from basyx.aas.adapter.aasx import AASXReader, DictSupplementaryFileContainer
from basyx.aas.model.provider import DictIdentifiableStore


def validate_aasx(path: Path) -> dict[str, object]:
    object_store = DictIdentifiableStore()
    file_store = DictSupplementaryFileContainer()
    with AASXReader(path, failsafe=False) as reader:
        identifiers = reader.read_into(object_store, file_store)

    if not identifiers:
        raise ValueError("AASX contains no identifiable AAS objects")

    return {
        "path": str(path),
        "identifiableCount": len(identifiers),
        "identifiableIds": sorted(str(identifier) for identifier in identifiers),
        "supplementaryFileCount": len(file_store),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="AASX package to validate")
    args = parser.parse_args()

    try:
        result = validate_aasx(args.package)
    except Exception as exc:  # noqa: BLE001 - CLI must report codec failures cleanly
        print(f"AASX INVALID: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
