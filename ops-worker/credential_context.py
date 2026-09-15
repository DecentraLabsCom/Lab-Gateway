"""Explicit dependencies for managed WinRM credential storage."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CredentialContext:
    """Credential-store implementation and its cache, filesystem and crypto ports."""

    load_fernet_impl: Callable[..., Any]
    get_cached_fernet: Callable[[], Optional[Any]]
    set_cached_fernet: Callable[[Any], None]
    get_load_fernet: Callable[[], Callable[[], Any]]
    get_read_secret: Callable[[], Callable[[str], str]]
    get_fernet_factory: Callable[[], Callable[[bytes], Any]]
    normalize_credential_ref: Callable[[Any], str]
    credential_ref_for_host: Callable[..., str]
    read_credentials_store_impl: Callable[[str], Dict[str, Any]]
    get_credentials_path: Callable[[], str]
    write_credentials_store_impl: Callable[[str, Dict[str, Any]], None]
    save_credentials_impl: Callable[..., None]
    load_credentials_impl: Callable[..., Optional[Dict[str, str]]]
    fernet_key_is_usable_impl: Callable[..., bool]
    get_logger: Callable[[], Any]


__all__ = ["CredentialContext"]
