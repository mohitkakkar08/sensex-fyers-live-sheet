from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from sensex_chain.auth import (
    REFRESH_URL,
    SEND_LOGIN_OTP_URL,
    TOKEN_URL,
    VALIDATE_AUTH_CODE_URL,
    VERIFY_OTP_URL,
    VERIFY_PIN_URL,
    AuthenticationError,
    AutomatedFyersTokenProvider,
    FallbackTokenProvider,
    FyersTokenProvider,
    totp_code,
)
from sensex_chain.config import RuntimeConfig


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, object]:
        return self._body


@dataclass(frozen=True)
class HttpCall:
    url: str
    payload: dict[str, object]
    timeout: int
    headers: dict[str, str] | None


class FakeHttp:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[HttpCall] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        timeout: int,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(HttpCall(url, json, timeout, headers))
        return self.responses.pop(0)


def config() -> RuntimeConfig:
    return RuntimeConfig(
        "app-100",
        "secret",
        "AB1234",
        "1234",
        "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
        "https://127.0.0.1/",
        "{}",
        "sheet",
        fyers_refresh_token="refresh",
    )


def test_refresh_uses_documented_hash_and_returns_access_token() -> None:
    http = FakeHttp([FakeResponse(200, {"s": "ok", "access_token": "token-value"})])

    assert FyersTokenProvider(config(), http).access_token() == "token-value"

    call = http.calls[0]
    assert call.url == REFRESH_URL
    assert call.payload["grant_type"] == "refresh_token"
    assert call.payload["appIdHash"] == hashlib.sha256(b"app-100:secret").hexdigest()
    assert call.payload["pin"] == "1234"
    assert call.timeout == 20


def test_refresh_failure_redacts_response_details() -> None:
    http = FakeHttp([FakeResponse(401, {"s": "error", "message": "secret must not leak"})])

    with pytest.raises(AuthenticationError) as error:
        FyersTokenProvider(config(), http).access_token()

    assert "secret" not in str(error.value)


def test_totp_code_matches_rfc6238_sha1_vector() -> None:
    assert totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59) == "287082"


def test_automated_login_exchanges_redirect_code_for_access_token() -> None:
    http = FakeHttp(
        [
            FakeResponse(200, {"request_key": "otp-request"}),
            FakeResponse(200, {"request_key": "pin-request"}),
            FakeResponse(200, {"data": {"access_token": "pin-token"}}),
            FakeResponse(308, {"Url": "https://127.0.0.1/?auth_code=one-time-code"}),
            FakeResponse(200, {"s": "ok", "access_token": "final-token"}),
        ]
    )

    assert AutomatedFyersTokenProvider(config(), http, lambda: 59).access_token() == "final-token"

    assert [call.url for call in http.calls] == [
        SEND_LOGIN_OTP_URL,
        VERIFY_OTP_URL,
        VERIFY_PIN_URL,
        TOKEN_URL,
        VALIDATE_AUTH_CODE_URL,
    ]
    assert http.calls[1].payload["otp"] == "287082"
    assert http.calls[3].headers == {"Authorization": "Bearer pin-token"}
    assert http.calls[4].payload["grant_type"] == "authorization_code"


def test_automated_login_failure_redacts_sensitive_response_details() -> None:
    http = FakeHttp([FakeResponse(401, {"message": "pin-token must not leak"})])

    with pytest.raises(AuthenticationError) as error:
        AutomatedFyersTokenProvider(config(), http, lambda: 59).access_token()

    assert "pin-token" not in str(error.value)


def test_fallback_provider_uses_refresh_only_after_automated_failure() -> None:
    class FailingProvider:
        def access_token(self) -> str:
            raise AuthenticationError("FYERS automated login failed")

    class WorkingProvider:
        def access_token(self) -> str:
            return "fallback-token"

    assert FallbackTokenProvider(FailingProvider(), WorkingProvider()).access_token() == "fallback-token"


