"""FYERS option-chain enrichment for fields not carried by SymbolUpdate."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import requests

from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain, INDEX_SYMBOL
from .rate_limit import FyersRequestGate

OPTION_CHAIN_TIMEOUT_SECONDS = 15


class OptionChainError(RuntimeError):
    """Raised when FYERS does not return a usable option-chain response."""


def extract_option_ticks(response: Mapping[str, Any], requested_symbols: set[str]) -> dict[str, dict[str, object]]:
    """Return the requested option records using stable internal field names."""
    if str(response.get("s", "ok")).lower() not in {"ok", "success"}:
        raise OptionChainError("OPTION_CHAIN_API_FAILED")
    result: dict[str, dict[str, object]] = {}
    for record in _records(response):
        symbol = str(record.get("symbol") or record.get("symbol_name") or "").strip()
        if symbol not in requested_symbols:
            continue
        values: dict[str, object] = {"symbol": symbol}
        for output, aliases in {
            "ltp": ("ltp", "lp"),
            "oi": ("oi", "open_interest", "OI"),
            "oi_change": ("oich", "oi_change", "change_in_oi", "OIch"),
            "iv": ("iv", "implied_volatility"),
            "delta": ("delta",),
            "gamma": ("gamma",),
            "theta": ("theta",),
            "vega": ("vega",),
            "rho": ("rho",),
        }.items():
            value = _lookup(record, aliases)
            if value is not None:
                values[output] = value
        result[symbol] = values
    if not result:
        raise OptionChainError("OPTION_CHAIN_NO_MATCHING_CONTRACTS")
    return result


def _records(value: object) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        flattened = dict(value)
        greeks = value.get("greeks")
        if isinstance(greeks, Mapping):
            flattened.update(greeks)
        if "symbol" in flattened or "symbol_name" in flattened:
            yield flattened
        for nested in value.values():
            yield from _records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _records(nested)


def _lookup(record: Mapping[str, Any], aliases: tuple[str, ...]) -> object | None:
    normalized = {"".join(character for character in str(key).lower() if character.isalnum()): value for key, value in record.items()}
    for alias in aliases:
        value = normalized.get("".join(character for character in alias.lower() if character.isalnum()))
        if value not in (None, ""):
            return value
    return None


class _TimeoutSession(requests.Session):
    def __init__(self, timeout_seconds: float) -> None:
        super().__init__()
        self._timeout_seconds = timeout_seconds

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout_seconds)
        return super().request(method, url, **kwargs)


class FyersOptionChainEnricher:
    """One bounded FYERS option-chain request per sheet refresh."""

    def __init__(self, client_id: str, token: str, model_factory: Callable[[str, str], object] | None = None, request_gate: FyersRequestGate | None = None) -> None:
        self._client_id = client_id
        self._token = token
        self._model_factory = model_factory or _sdk_option_chain_model
        self._model: object | None = None
        self._request_gate = request_gate or FyersRequestGate()
        self.diagnostic_code = "OPTION_CHAIN_NOT_STARTED"

    def refresh(self, chain: CurrentExpiryChain, cache: LatestMarketCache) -> None:
        permission = self._request_gate.acquire()
        if not permission.allowed:
            self.diagnostic_code = f"RATE_LIMIT_BACKOFF_{permission.retry_in_seconds}S"
            return
        try:
            response = self._client().optionchain(data={"symbol": INDEX_SYMBOL, "strikecount": _strike_count(chain), "timestamp": "", "greeks": "1"})
            if _is_rate_limited(response):
                delay = self._request_gate.on_rate_limit(_retry_after_seconds(response))
                self.diagnostic_code = f"RATE_LIMIT_BACKOFF_{delay}S"
                return
            ticks = extract_option_ticks(response, chain.option_symbols)
            for tick in ticks.values():
                cache.upsert(tick)
            self._request_gate.on_success()
            self.diagnostic_code = "OPTION_CHAIN_OK"
        except OptionChainError as exc:
            self.diagnostic_code = str(exc)
        except requests.Timeout:
            self.diagnostic_code = "OPTION_CHAIN_TIMEOUT"
        except Exception:
            self.diagnostic_code = "OPTION_CHAIN_REQUEST_FAILED"

    def _client(self) -> object:
        if self._model is None:
            self._model = self._model_factory(self._client_id, self._token)
        return self._model


def _strike_count(chain: CurrentExpiryChain) -> int:
    # The FYERS API returns this many strikes on each side of ATM. Requesting the
    # expiry's full strike count ensures every contract shown in Sheets is eligible.
    return max(1, len(chain.strike_pairs))


def _is_rate_limited(response: object) -> bool:
    if not isinstance(response, Mapping):
        return False
    code = str(response.get("code", ""))
    message = str(response.get("message", "")).lower()
    return code == "429" or "rate limit" in message or "request limit" in message


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


def _sdk_option_chain_model(client_id: str, token: str) -> object:
    from fyers_apiv3 import fyersModel

    model = fyersModel.FyersModel(client_id=client_id, token=token, is_async=False)
    service = getattr(model, "service", None)
    if isinstance(getattr(service, "session", None), requests.Session):
        service.session = _TimeoutSession(OPTION_CHAIN_TIMEOUT_SECONDS)
    return model
