"""FYERS option-chain enrichment for fields not carried by SymbolUpdate."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain, INDEX_SYMBOL
from typing import Any


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
            "ltp": ("ltp", "lp"), "oi": ("oi", "open_interest", "OI"),
            "oi_change": ("oich", "oi_change", "change_in_oi", "OIch"),
            "iv": ("iv", "implied_volatility"), "delta": ("delta",), "gamma": ("gamma",),
            "theta": ("theta",), "vega": ("vega",), "rho": ("rho",),
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
class FyersOptionChainEnricher:
    """One bounded FYERS option-chain request per sheet refresh."""

    def __init__(self, client_id: str, token: str, model_factory: Callable[[str, str], object] | None = None) -> None:
        self._client_id = client_id
        self._token = token
        self._model_factory = model_factory or _sdk_option_chain_model
        self.diagnostic_code = "OPTION_CHAIN_NOT_STARTED"

    def refresh(self, chain: CurrentExpiryChain, cache: LatestMarketCache) -> None:
        try:
            response = self._model_factory(self._client_id, self._token).optionchain(data={"symbol": INDEX_SYMBOL, "strikecount": 0, "timestamp": "", "greeks": "1"})
            ticks = extract_option_ticks(response, {contract.symbol for contract in chain.contracts})
            for tick in ticks.values():
                cache.upsert(tick)
            self.diagnostic_code = "OPTION_CHAIN_OK"
        except OptionChainError as exc:
            self.diagnostic_code = str(exc)
        except Exception:
            self.diagnostic_code = "OPTION_CHAIN_REQUEST_FAILED"


def _sdk_option_chain_model(client_id: str, token: str) -> object:
    from fyers_apiv3 import fyersModel
    return fyersModel.FyersModel(client_id=client_id, token=token, is_async=False)