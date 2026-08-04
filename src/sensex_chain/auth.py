"""FYERS refresh-token exchange for a data-only worker session."""

from __future__ import annotations

import hashlib
from typing import Protocol

from .config import RuntimeConfig


REFRESH_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"


class AuthenticationError(RuntimeError):
    """Raised when FYERS cannot create an access token."""


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> dict[str, object]: ...


class HttpClient(Protocol):
    def post(self, url: str, *, json: dict[str, object], timeout: int) -> HttpResponse: ...


class FyersTokenProvider:
    """Exchanges a configured refresh token for a single worker access token."""

    def __init__(self, config: RuntimeConfig, http: HttpClient) -> None:
        self._config = config
        self._http = http

    def access_token(self) -> str:
        app_id_hash = hashlib.sha256(
            f"{self._config.fyers_client_id}:{self._config.fyers_secret_key}".encode("utf-8")
        ).hexdigest()
        response = self._http.post(
            REFRESH_URL,
            json={
                "grant_type": "refresh_token",
                "appIdHash": app_id_hash,
                "refresh_token": self._config.fyers_refresh_token,
                "pin": self._config.fyers_pin,
            },
            timeout=20,
        )
        body = response.json()
        token = body.get("access_token")
        if response.status_code != 200 or body.get("s") != "ok" or not isinstance(token, str):
            raise AuthenticationError(
                "FYERS refresh-token exchange failed; replace the expired refresh token if needed"
            )
        return token
