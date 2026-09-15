"""Explicit dependencies for request and policy input normalization."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class InputContext:
    """Pure normalizers used by request handlers and runtime configuration."""

    coerce_bool: Callable[[Any], Optional[bool]]
    parse_bool: Callable[[Any, bool], bool]
    normalize_args: Callable[[Any, Optional[List[str]]], List[str]]
    parse_recipients: Callable[[Any, Optional[List[str]]], List[str]]


__all__ = ["InputContext"]
