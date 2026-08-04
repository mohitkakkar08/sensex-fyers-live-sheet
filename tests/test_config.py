from __future__ import annotations

import pytest

from sensex_chain.config import ConfigurationError, RuntimeConfig


def valid_environ() -> dict[str, str]:
    return {
        "FYERS_CLIENT_ID": "app-100",
        "FYERS_SECRET_KEY": "super-secret",
        "FYERS_USER_ID": "AB1234",
        "FYERS_PIN": "1234",
        "FYERS_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
        "FYERS_REDIRECT_URI": "https://127.0.0.1/",
        "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type":"service_account"}',
        "GOOGLE_SHEET_ID": "sheet-id",
    }


def test_from_environ_requires_automated_login_values() -> None:
    environ = valid_environ()
    del environ["FYERS_TOTP_SECRET"]

    with pytest.raises(ConfigurationError, match="FYERS_TOTP_SECRET"):
        RuntimeConfig.from_environ(environ)


def test_from_environ_uses_default_cadence_and_redacts_secrets() -> None:
    config = RuntimeConfig.from_environ(valid_environ())

    assert config.flush_seconds == 10
    assert config.fyers_refresh_token is None
    assert "super-secret" not in repr(config)
    assert "1234" not in repr(config)
