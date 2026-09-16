import json
import logging
from typing import Dict, Optional, cast

import pytest
from cryptography.fernet import Fernet

from winrm_credential_store import (
    decrypt_secret,
    encrypt_secret,
    fernet_key_is_usable,
    load_credentials,
    load_fernet,
    read_credentials_store,
    save_credentials,
    write_credentials_store,
)


def test_load_fernet_contract_reuses_cache_and_requires_a_key():
    cached = cast(Fernet, object())
    assert load_fernet(cached, read_secret=lambda _name: "unused") is cached

    with pytest.raises(RuntimeError, match="OPS_SECRETS_KEY is required"):
        load_fernet(None, read_secret=lambda _name: "")


def test_fernet_key_health_probe_preserves_success_and_failure_contract():
    calls = []
    logger = type("Logger", (), {"warning": lambda self, *args: calls.append(args)})()

    assert fernet_key_is_usable(
        load_fernet=lambda: cast(Fernet, object()), logger=logger
    ) is True

    def fail():
        raise ValueError("invalid")

    assert fernet_key_is_usable(load_fernet=fail, logger=logger) is False
    assert calls == [("OPS_SECRETS_KEY is unavailable or invalid: %s", "ValueError")]


def test_secret_helpers_preserve_utf8_round_trip_and_ascii_ciphertext():
    key = Fernet.generate_key()
    fernet = Fernet(key)

    encrypted = encrypt_secret("contraseña-éxito", load_fernet=lambda: fernet)

    assert encrypted.isascii()
    assert decrypt_secret(encrypted, load_fernet=lambda: fernet) == "contraseña-éxito"


def test_credential_store_contract_encrypts_and_round_trips_without_plaintext(
    tmp_path,
):
    key = Fernet.generate_key().decode("ascii")
    path = tmp_path / "credentials.json"
    cache: Dict[str, Optional[Fernet]] = {"value": None}

    def get_fernet():
        cache["value"] = load_fernet(
            cache["value"],
            read_secret=lambda _name: key,
        )
        return cache["value"]

    save_credentials(
        " LAB-WS-01 ",
        " .\\LabGatewaySvc ",
        "secret-password",
        normalize_ref=lambda value: str(value or "").strip().lower(),
        load_fernet=get_fernet,
        read_store=lambda: read_credentials_store(str(path)),
        write_store=lambda data: write_credentials_store(str(path), data),
    )

    raw = path.read_text(encoding="utf-8")
    assert "secret-password" not in raw
    assert load_credentials(
        "lab-ws-01",
        normalize_ref=lambda value: str(value or "").strip().lower(),
        load_fernet=get_fernet,
        read_store=lambda: read_credentials_store(str(path)),
        logger=logging,
    ) == {"user": ".\\LabGatewaySvc", "password": "secret-password"}


def test_credential_store_contract_preserves_invalid_entries_and_atomic_store_shape(tmp_path):
    path = tmp_path / "nested" / "credentials.json"
    write_credentials_store(str(path), {"unexpected": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"unexpected": True}
    assert read_credentials_store(str(path)) == {"unexpected": True, "credentials": {}}

    with pytest.raises(ValueError, match="credentialRef is required"):
        save_credentials(
            "",
            "user",
            "password",
            normalize_ref=lambda value: str(value or "").strip().lower(),
            load_fernet=lambda: cast(Fernet, object()),
            read_store=lambda: {"credentials": {}},
            write_store=lambda _data: None,
        )
