"""Composition adapter for managed WinRM credential storage."""

from typing import Any, Dict, Optional

from credential_context import CredentialContext


class CredentialRuntime:
    """Expose credential storage through explicit dependency ports."""

    def __init__(self, context: CredentialContext):
        self._context = context

    def load_fernet(self) -> Any:
        value = self._context.load_fernet_impl(
            self._context.get_cached_fernet(),
            read_secret=self._context.get_read_secret(),
            fernet_factory=self._context.get_fernet_factory(),
        )
        self._context.set_cached_fernet(value)
        return value

    def normalize_credential_ref(self, value: Any) -> str:
        return self._context.normalize_credential_ref(value)

    def credential_ref_for_host(self, host: Dict[str, Any]) -> str:
        return self._context.credential_ref_for_host(
            host,
            normalize_ref=self.normalize_credential_ref,
        )

    def read_winrm_credentials_store(self) -> Dict[str, Any]:
        return self._context.read_credentials_store_impl(
            self._context.get_credentials_path()
        )

    def write_winrm_credentials_store(self, data: Dict[str, Any]) -> None:
        return self._context.write_credentials_store_impl(
            self._context.get_credentials_path(),
            data,
        )

    def save_winrm_credentials(self, credential_ref: str, user: str, password: str) -> None:
        return self._context.save_credentials_impl(
            credential_ref,
            user,
            password,
            normalize_ref=self.normalize_credential_ref,
            load_fernet=self.load_fernet,
            read_store=self.read_winrm_credentials_store,
            write_store=self.write_winrm_credentials_store,
        )

    def load_winrm_credentials(self, credential_ref: str) -> Optional[Dict[str, str]]:
        return self._context.load_credentials_impl(
            credential_ref,
            normalize_ref=self.normalize_credential_ref,
            load_fernet=self.load_fernet,
            read_store=self.read_winrm_credentials_store,
            logger=self._context.get_logger(),
        )

    def winrm_credentials_configured(self, credential_ref: str) -> bool:
        return self.load_winrm_credentials(credential_ref) is not None

    def fernet_key_is_usable(self) -> bool:
        return self._context.fernet_key_is_usable_impl(
            load_fernet=self._context.get_load_fernet(),
            logger=self._context.get_logger(),
        )


def create_credential_runtime(context: CredentialContext) -> CredentialRuntime:
    """Create a credential adapter bound to explicit ports."""
    return CredentialRuntime(context)


__all__ = ["CredentialRuntime", "create_credential_runtime"]
