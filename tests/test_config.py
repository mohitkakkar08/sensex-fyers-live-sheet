from __future__ import annotations

import pytest

from sensex_chain.config import ConfigurationError, RuntimeConfig


def valid_environ() -> dict[str, str]:
    return {
        "FYERS_CLIENT_ID": "app",
        "FYERS_SECRET_KEY": "super-secret",
        "FYERS_REFRESH_TOKEN": "refresh-token",
        "FYERS_PIN": "1234",
        "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type":"service_account"}',
        "GOOGLE_SHEET_ID": "sheet-id",
    }


def test_from_environ_requires_all_runtime_secrets() -> None:
    with pytest.raises(ConfigurationError, match="FYERS_PIN"):
        RuntimeConfig.from_environ({"FYERS_CLIENT_ID": "app"})


def test_from_environ_uses_default_cadence_and_redacts_secrets() -> None:
    config = RuntimeConfig.from_environ(valid_environ())

    assert config.flush_seconds == 10
    assert "super-secret" not in repr(config)
    assert "1234" not in repr(config)
