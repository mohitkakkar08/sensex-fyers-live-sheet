"""Rate-limited FYERS market-depth enrichment for the selected SENSEX future."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import requests

from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain
from .option_chain import _sdk_option_chain_model
from .rate_limit import FyersRequestGate


class FutureDepthError(RuntimeError):
    """Raised when FYERS does not provide usable futures OI data."""


def extract_future_depth_tick(response: Mapping[str, Any], symbol: str) -> dict[str, object]:
    if str(response.get("s", "ok")).lower() not in {"ok", "success"}:
        raise FutureDepthError("FUTURE_DEPTH_API_FAILED")
    record = _find_symbol_record(response, symbol)
    if record is None:
        raise FutureDepthError("FUTURE_DEPTH_SYMBOL_MISSING")
    oi = _lookup(record, ("oi", "open_interest", "openinterest"))
    if oi is None:
        raise FutureDepthError("FUTURE_DEPTH_OI_MISSING")
    result: dict[str, object] = {"symbol": symbol, "oi": oi}
    change = _lookup(record, ("oich", "oi_change", "change_in_oi", "changeinoi"))
    if change is None:
        previous_oi = _lookup(record, ("pdoi", "previous_oi", "prev_oi", "previous_open_interest"))
        if previous_oi is not None:
            try:
                change = float(oi) - float(previous_oi)
            except (TypeError, ValueError):
                change = None
    if change is not None:
        result["oi_change"] = change
    return result


def _find_symbol_record(value: object, symbol: str) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    direct = value.get(symbol)
    if isinstance(direct, Mapping):
        view = direct.get("v")
        return view if isinstance(view, Mapping) else direct
    if str(value.get("symbol") or value.get("symbol_name") or "").strip() == symbol:
        view = value.get("v")
        return view if isinstance(view, Mapping) else value
    for nested in value.values():
        record = _find_symbol_record(nested, symbol)
        if record is not None:
            return record
    return None


def _lookup(record: Mapping[str, Any], aliases: tuple[str, ...]) -> object | None:
    normalized = {"".join(character for character in str(key).lower() if character.isalnum()): value for key, value in record.items()}
    for alias in aliases:
        value = normalized.get("".join(character for character in alias.lower() if character.isalnum()))
        if value not in (None, ""):
            return value
    return None


def _is_rate_limited(response: object) -> bool:
    if not isinstance(response, Mapping):
        return False
    return str(response.get("code", "")) == "429" or "rate limit" in str(response.get("message", "")).lower()


def _retry_after_seconds(response: object) -> float | None:
    if not isinstance(response, Mapping):
        return None
    for name in ("retry_after", "retryAfter"):
        try:
            value = float(response[name])
        except (KeyError, TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


class FyersFutureDepthEnricher:
    """Fetch exactly one future-depth record at a conservative 15-second cadence."""

    def __init__(self, client_id: str, token: str, model_factory: Callable[[str, str], object] | None = None, request_gate: FyersRequestGate | None = None) -> None:
        self._client_id = client_id
        self._token = token
        self._model_factory = model_factory or _sdk_option_chain_model
        self._model: object | None = None
        self._request_gate = request_gate or FyersRequestGate(minimum_interval_seconds=15.0)
        self.diagnostic_code = "FUTURE_DEPTH_NOT_STARTED"

    def refresh(self, chain: CurrentExpiryChain, cache: LatestMarketCache) -> None:
        if chain.future is None:
            self.diagnostic_code = "FUTURE_DEPTH_NOT_APPLICABLE"
            return
        permission = self._request_gate.acquire()
        if not permission.allowed:
            self.diagnostic_code = f"FUTURE_DEPTH_THROTTLED_{permission.retry_in_seconds}S"
            return
        try:
            response = self._client().depth(data={"symbol": chain.future.symbol, "ohlcv_flag": "1"})
            if _is_rate_limited(response):
                delay = self._request_gate.on_rate_limit(_retry_after_seconds(response))
                self.diagnostic_code = f"FUTURE_DEPTH_RATE_LIMIT_BACKOFF_{delay}S"
                return
            cache.upsert(extract_future_depth_tick(response, chain.future.symbol))
            self._request_gate.on_success()
            self.diagnostic_code = "FUTURE_DEPTH_OK"
        except FutureDepthError as exc:
            self.diagnostic_code = str(exc)
        except requests.Timeout:
            self.diagnostic_code = "FUTURE_DEPTH_TIMEOUT"
        except Exception:
            self.diagnostic_code = "FUTURE_DEPTH_REQUEST_FAILED"

    def _client(self) -> object:
        if self._model is None:
            self._model = self._model_factory(self._client_id, self._token)
        return self._model
