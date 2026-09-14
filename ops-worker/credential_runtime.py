"""Composition adapter for managed WinRM credential storage."""

from collections.abc import Mapping
from typing import Any, Dict, Optional


class CredentialRuntime:
    """Resolve credential storage operations from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def load_fernet(self) -> Any:
        get = self._get
        value = get("_load_fernet_store_impl")(
            get("_FERNET"),
            read_secret=get("_env_or_secret_file"),
            fernet_factory=get("Fernet"),
        )
        if hasattr(self._providers, "__setitem__"):
            self._providers["_FERNET"] = value
        return value

    def normalize_credential_ref(self, value: Any) -> str:
        return self._get("_normalize_credential_ref_impl")(value)

    def credential_ref_for_host(self, host: Dict[str, Any]) -> str:
        return self._get("_credential_ref_for_host_impl")(
            host,
            normalize_ref=self._get("normalize_credential_ref"),
        )

    def read_winrm_credentials_store(self) -> Dict[str, Any]:
        return self._get("_read_credentials_store_impl")(
            self._get("OPS_CREDENTIALS_PATH")
        )

    def write_winrm_credentials_store(self, data: Dict[str, Any]) -> None:
        return self._get("_write_credentials_store_impl")(
            self._get("OPS_CREDENTIALS_PATH"),
            data,
        )

    def save_winrm_credentials(self, credential_ref: str, user: str, password: str) -> None:
        get = self._get
        return get("_save_credentials_store_impl")(
            credential_ref,
            user,
            password,
            normalize_ref=get("normalize_credential_ref"),
            load_fernet=get("_load_fernet"),
            read_store=get("read_winrm_credentials_store"),
            write_store=get("write_winrm_credentials_store"),
        )

    def load_winrm_credentials(self, credential_ref: str) -> Optional[Dict[str, str]]:
        get = self._get
        return get("_load_credentials_store_impl")(
            credential_ref,
            normalize_ref=get("normalize_credential_ref"),
            load_fernet=get("_load_fernet"),
            read_store=get("read_winrm_credentials_store"),
            logger=get("logging"),
        )

    def winrm_credentials_configured(self, credential_ref: str) -> bool:
        return self._get("load_winrm_credentials")(credential_ref) is not None

    def fernet_key_is_usable(self) -> bool:
        get = self._get
        return get("_fernet_key_is_usable_impl")(
            load_fernet=get("_load_fernet"),
            logger=get("logging"),
        )


def create_credential_runtime(providers: Mapping[str, Any]) -> CredentialRuntime:
    """Create a credential adapter bound to live providers."""
    return CredentialRuntime(providers)


__all__ = ["CredentialRuntime", "create_credential_runtime"]
