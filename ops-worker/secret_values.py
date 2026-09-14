"""Small helpers for loading secrets from environment variables or files."""

import logging
import os
from typing import Any


_LOGGER = logging.getLogger(__name__)


def env_or_secret_file(
    name: str,
    default: str = "",
    *,
    logger: Any = None,
) -> str:
    """Read an environment value, falling back to a trimmed mounted secret."""
    value = os.getenv(name)
    if value:
        return value
    path = os.getenv(f"{name}_FILE")
    if not path:
        return default
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        (logger or _LOGGER).warning("Unable to read secret file for %s", name)
        return default
