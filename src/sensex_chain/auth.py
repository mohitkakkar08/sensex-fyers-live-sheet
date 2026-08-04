"""FYERS token providers for the data-only worker session."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
from collections.abc import Callable
from typing import Protocol
from urllib.parse import parse_qs, urlparse

from .config import RuntimeConfig


REFRESH_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
SEND_LOGIN_OTP_URL = "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2"
VERIFY_OTP_URL = "https://api-t2.fyers.in/vagator/v2/verify_otp"
VERIFY_PIN_URL = "https://api-t2.fyers.in/vagator/v2/verify_pin_v2"
TOKEN_URL = "https://api-t1.fyers.in/api/v3/token"
VALIDATE_AUTH_CODE_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"


class AuthenticationError(RuntimeError):
    """Raised when FYERS cannot create an access token."""


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> dict[str, object]: ...


class HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        timeout: int,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse: ...


class TokenProvider(Protocol):
    def access_token(self) -> str: ...


def totp_code(secret: str, unix_time: int) -> str:
    """Return a six-digit RFC 6238 SHA-1 TOTP without persisting the secret."""

    try:
        normalized = secret.strip().replace(" ", "").upper()
        key = base64.b32decode(normalized, casefold=True)
        digest = hmac.new(key, struct.pack(">Q", unix_time // 30), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    except (ValueError, binascii.Error, struct.error):
        raise AuthenticationError("FYERS automated login failed") from None
    return f"{value:06d}"


class FyersTokenProvider:
    """Exchanges an optional configured refresh token for an access token."""

    def __init__(self, config: RuntimeConfig, http: HttpClient) -> None:
        self._config = config
        self._http = http

    def access_token(self) -> str:
        refresh_token = self._config.fyers_refresh_token
        if not refresh_token:
            raise AuthenticationError("FYERS refresh-token exchange failed")
        app_id_hash = hashlib.sha256(
            f"{self._config.fyers_client_id}:{self._config.fyers_secret_key}".encode("utf-8")
        ).hexdigest()
        response = self._http.post(
            REFRESH_URL,
            json={
                "grant_type": "refresh_token",
                "appIdHash": app_id_hash,
                "refresh_token": refresh_token,
                "pin": self._config.fyers_pin,
            },
            timeout=20,
        )
        body = _response_body(response)
        token = body.get("access_token")
        if response.status_code != 200 or body.get("s") != "ok" or not isinstance(token, str):
            raise AuthenticationError("FYERS refresh-token exchange failed")
        return token


class AutomatedFyersTokenProvider:
    """Creates a worker token from the configured FYERS External TOTP."""

    def __init__(
        self,
        config: RuntimeConfig,
        http: HttpClient,
        unix_time: Callable[[], int],
    ) -> None:
        self._config = config
        self._http = http
        self._unix_time = unix_time

    def access_token(self) -> str:
        try:
            otp_request = self._request_key(
                SEND_LOGIN_OTP_URL,
                {
                    "fy_id": _base64_ascii(self._config.fyers_user_id),
                    "app_id": "2",
                },
            )
            pin_request = self._request_key(
                VERIFY_OTP_URL,
                {
                    "request_key": otp_request,
                    "otp": totp_code(self._config.fyers_totp_secret, self._unix_time()),
                },
            )
            pin_token = self._pin_token(pin_request)
            auth_code = self._authorization_code(pin_token)
            return self._validate_auth_code(auth_code)
        except AuthenticationError:
            raise
        except (ValueError, UnicodeError, KeyError, TypeError):
            raise AuthenticationError("FYERS automated login failed") from None

    def _request_key(self, url: str, payload: dict[str, object]) -> str:
        response = self._http.post(url, json=payload, timeout=20)
        body = _response_body(response)
        request_key = body.get("request_key")
        if response.status_code != 200 or not isinstance(request_key, str) or not request_key:
            raise AuthenticationError("FYERS automated login failed")
        return request_key

    def _pin_token(self, request_key: str) -> str:
        response = self._http.post(
            VERIFY_PIN_URL,
            json={
                "request_key": request_key,
                "identity_type": "pin",
                "identifier": _base64_ascii(self._config.fyers_pin),
            },
            timeout=20,
        )
        body = _response_body(response)
        data = body.get("data")
        token = data.get("access_token") if isinstance(data, dict) else None
        if response.status_code != 200 or not isinstance(token, str) or not token:
            raise AuthenticationError("FYERS automated login failed")
        return token

    def _authorization_code(self, pin_token: str) -> str:
        app_id, app_type = _app_parts(self._config.fyers_client_id)
        response = self._http.post(
            TOKEN_URL,
            json={
                "fyers_id": self._config.fyers_user_id,
                "app_id": app_id,
                "redirect_uri": self._config.fyers_redirect_uri,
                "appType": app_type,
                "code_challenge": "",
                "state": "",
                "scope": "",
                "nonce": "",
                "response_type": "code",
                "create_cookie": True,
            },
            headers={"Authorization": f"Bearer {pin_token}"},
            timeout=20,
        )
        body = _response_body(response)
        redirect_url = body.get("Url")
        auth_codes = (
            parse_qs(urlparse(redirect_url).query).get("auth_code", [])
            if isinstance(redirect_url, str)
            else []
        )
        if response.status_code != 308 or not auth_codes or not auth_codes[0]:
            raise AuthenticationError("FYERS automated login failed")
        return auth_codes[0]

    def _validate_auth_code(self, auth_code: str) -> str:
        app_id_hash = hashlib.sha256(
            f"{self._config.fyers_client_id}:{self._config.fyers_secret_key}".encode("utf-8")
        ).hexdigest()
        response = self._http.post(
            VALIDATE_AUTH_CODE_URL,
            json={
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash,
                "code": auth_code,
            },
            timeout=20,
        )
        body = _response_body(response)
        token = body.get("access_token")
        if response.status_code != 200 or body.get("s") != "ok" or not isinstance(token, str):
            raise AuthenticationError("FYERS automated login failed")
        return token


class FallbackTokenProvider:
    """Uses the legacy refresh flow only after automated authentication fails."""

    def __init__(self, primary: TokenProvider, fallback: TokenProvider | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def access_token(self) -> str:
        try:
            return self._primary.access_token()
        except AuthenticationError:
            if self._fallback is None:
                raise
            return self._fallback.access_token()


def _response_body(response: HttpResponse) -> dict[str, object]:
    try:
        body = response.json()
    except (TypeError, ValueError):
        raise AuthenticationError("FYERS automated login failed") from None
    if not isinstance(body, dict):
        raise AuthenticationError("FYERS automated login failed")
    return body


def _base64_ascii(value: str) -> str:
    return base64.b64encode(value.encode("ascii")).decode("ascii")


def _app_parts(client_id: str) -> tuple[str, str]:
    app_id, separator, app_type = client_id.rpartition("-")
    if not separator or not app_id or not app_type:
        raise AuthenticationError("FYERS automated login failed")
    return app_id, app_type
