from __future__ import annotations

import hashlib

import pytest

from sensex_chain.auth import AuthenticationError, FyersTokenProvider, REFRESH_URL
from sensex_chain.config import RuntimeConfig


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, object]:
        return self._body


class FakeHttp:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def post(self, url: str, *, json: dict[str, object], timeout: int) -> FakeResponse:
        self.calls.append((url, json, timeout))
        return self.response


def config() -> RuntimeConfig:
    return RuntimeConfig("app", "secret", "refresh", "1234", "{}", "sheet")


def test_refresh_uses_documented_hash_and_returns_access_token() -> None:
    http = FakeHttp(FakeResponse(200, {"s": "ok", "access_token": "token-value"}))

    assert FyersTokenProvider(config(), http).access_token() == "token-value"

    url, payload, timeout = http.calls[0]
    assert url == REFRESH_URL
    assert payload["grant_type"] == "refresh_token"
    assert payload["appIdHash"] == hashlib.sha256(b"app:secret").hexdigest()
    assert payload["pin"] == "1234"
    assert timeout == 20


def test_refresh_failure_redacts_response_details() -> None:
    http = FakeHttp(FakeResponse(401, {"s": "error", "message": "secret must not leak"}))

    with pytest.raises(AuthenticationError) as error:
        FyersTokenProvider(config(), http).access_token()

    assert "secret" not in str(error.value)
