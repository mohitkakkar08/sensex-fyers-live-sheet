"""Runtime configuration sourced only from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when a required runtime setting is missing or invalid."""


@dataclass(frozen=True, repr=False)
class RuntimeConfig:
    """Secrets and non-secret controls required by one worker run."""

    fyers_client_id: str
    fyers_secret_key: str
    fyers_user_id: str
    fyers_pin: str
    fyers_totp_secret: str
    fyers_redirect_uri: str
    google_service_account_json: str
    sheet_id: str
    fyers_refresh_token: str | None = None
    flush_seconds: int = 10

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "RuntimeConfig":
        required = (
            "FYERS_CLIENT_ID",
            "FYERS_SECRET_KEY",
            "FYERS_USER_ID",
            "FYERS_PIN",
            "FYERS_TOTP_SECRET",
            "FYERS_REDIRECT_URI",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "GOOGLE_SHEET_ID",
        )
        missing = [name for name in required if not environ.get(name, "").strip()]
        if missing:
            raise ConfigurationError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )
        return cls(
            *(environ[name] for name in required),
            fyers_refresh_token=environ.get("FYERS_REFRESH_TOKEN", "").strip() or None,
        )

    def __repr__(self) -> str:
        return "RuntimeConfig(redacted=True, flush_seconds=%d)" % self.flush_seconds
