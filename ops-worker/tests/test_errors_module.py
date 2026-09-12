import errors


def test_winrm_error_contract_is_exposed_from_the_dedicated_module():
    error = errors.WinRMTrustError(
        errors.WINRM_TRUST_REQUIRED_CODE,
        errors.WINRM_TRUST_REQUIRED_MESSAGE,
    )

    assert isinstance(error, ValueError)
    assert error.code == "WINRM_TRUST_REQUIRED"
    assert str(error) == "WinRM certificate trust is required"
    assert errors.WINRM_TRUST_ERROR_MESSAGES[error.code] == str(error)


def test_missing_credentials_predicate_preserves_the_existing_error_message():
    missing = ValueError(errors.WINRM_CREDENTIALS_REQUIRED_MESSAGE)

    assert errors.is_missing_winrm_credentials_error(missing) is True
    assert errors.is_missing_winrm_credentials_error(ValueError("other")) is False
    assert errors.is_missing_winrm_credentials_error(RuntimeError(str(missing))) is False
