"""FYERS BSE derivatives-master parsing and current-expiry selection."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import cached_property
from typing import Iterable, Sequence

INSTRUMENT_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"
INDEX_SYMBOL = "BSE:SENSEX-INDEX"
INDIA_VIX_SYMBOL = "NSE:INDIAVIX-INDEX"


class InstrumentDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str


@dataclass(frozen=True)
class FutureContract:
    symbol: str
    underlying: str
    expiry: date


@dataclass(frozen=True)
class CurrentExpiryChain:
    expiry: date
    contracts: tuple[OptionContract, ...]
    future: FutureContract | None = None

    @cached_property
    def symbols(self) -> tuple[str, ...]:
        future_symbols = (self.future.symbol,) if self.future is not None else ()
        return (INDEX_SYMBOL, INDIA_VIX_SYMBOL) + tuple(contract.symbol for contract in self.contracts) + future_symbols

    @cached_property
    def option_symbols(self) -> frozenset[str]:
        return frozenset(contract.symbol for contract in self.contracts)

    @cached_property
    def strike_pairs(self) -> tuple[tuple[Decimal, OptionContract, OptionContract], ...]:
        by_strike: dict[Decimal, dict[str, OptionContract]] = {}
        for contract in self.contracts:
            by_strike.setdefault(contract.strike, {})[contract.option_type] = contract
        return tuple(
            (strike, contracts["CE"], contracts["PE"])
            for strike, contracts in sorted(by_strike.items())
            if "CE" in contracts and "PE" in contracts
        )


class FyersInstrumentCatalog:
    def __init__(self, contracts: Iterable[OptionContract], futures: Iterable[FutureContract] = ()) -> None:
        self._contracts = tuple(contracts)
        self._futures = tuple(futures)

    @classmethod
    def from_csv(cls, contents: str) -> "FyersInstrumentCatalog":
        rows = list(csv.reader(io.StringIO(contents)))
        if not rows:
            raise InstrumentDiscoveryError("INSTRUMENT_MASTER_EMPTY")
        contracts: list[OptionContract] = []
        futures: list[FutureContract] = []
        header = {_normalize_header(value) for value in rows[0]}
        if "symbolticker" in header or "underlyingsymbol" in header:
            for row in csv.DictReader(io.StringIO(contents)):
                contract = _parse_named(row)
                future = _parse_named_future(row)
                if contract:
                    contracts.append(contract)
                if future:
                    futures.append(future)
        else:
            for row in rows:
                contract = _parse_positional(row)
                future = _parse_positional_future(row)
                if contract:
                    contracts.append(contract)
                if future:
                    futures.append(future)
        return cls(contracts, futures)

    @classmethod
    def download(cls, http: object) -> "FyersInstrumentCatalog":
        try:
            response = http.get(INSTRUMENT_MASTER_URL, timeout=30)
            response.raise_for_status()
            return cls.from_csv(response.text)
        except InstrumentDiscoveryError:
            raise
        except Exception:
            raise InstrumentDiscoveryError("INSTRUMENT_MASTER_DOWNLOAD") from None

    def current_sensex_chain(self, today: date) -> CurrentExpiryChain:
        candidates = [contract for contract in self._contracts if contract.underlying == "SENSEX" and contract.expiry >= today]
        if not candidates:
            raise InstrumentDiscoveryError("INSTRUMENT_MASTER_NO_SENSEX_OPTIONS")
        for expiry in sorted({contract.expiry for contract in candidates}):
            contracts = tuple(sorted((contract for contract in candidates if contract.expiry == expiry), key=lambda contract: (contract.strike, contract.option_type, contract.symbol)))
            if {"CE", "PE"}.issubset({contract.option_type for contract in contracts}):
                futures = [future for future in self._futures if future.underlying == "SENSEX" and future.expiry >= today]
                future = min(futures, key=lambda item: (item.expiry, item.symbol)) if futures else None
                return CurrentExpiryChain(expiry, contracts, future)
        raise InstrumentDiscoveryError("INSTRUMENT_MASTER_NO_VALID_EXPIRY")


def chunk_subscriptions(symbols: Sequence[str], max_symbols: int = 200) -> list[list[str]]:
    if max_symbols < 1:
        raise ValueError("max_symbols must be positive")
    return [list(symbols[index:index + max_symbols]) for index in range(0, len(symbols), max_symbols)]


def _parse_positional(row: list[str]) -> OptionContract | None:
    if len(row) < 14 or row[13].strip().upper() != "SENSEX":
        return None
    match = re.search(r"\s(\d+(?:\.\d+)?)\s+(CE|PE)\s*$", row[1].strip(), re.I)
    if not match:
        return None
    try:
        return OptionContract(row[9].strip(), "SENSEX", datetime.fromtimestamp(int(float(row[8])), tz=timezone.utc).date(), Decimal(match.group(1)), match.group(2).upper())
    except (ValueError, InvalidOperation, IndexError):
        return None


def _parse_positional_future(row: list[str]) -> FutureContract | None:
    if len(row) < 14 or row[13].strip().upper() != "SENSEX" or not row[9].strip().upper().endswith("FUT"):
        return None
    try:
        return FutureContract(row[9].strip(), "SENSEX", datetime.fromtimestamp(int(float(row[8])), tz=timezone.utc).date())
    except (ValueError, IndexError):
        return None


def _parse_named(row: dict[str, str | None]) -> OptionContract | None:
    normalized = {_normalize_header(key): (value or "").strip() for key, value in row.items() if key}
    symbol = _value(normalized, "symbolticker", "symbol")
    underlying = _value(normalized, "underlyingsymbol", "underlying").upper()
    option_type = _value(normalized, "optiontype").upper()
    if not symbol or underlying != "SENSEX" or option_type not in {"CE", "PE"}:
        return None
    try:
        return OptionContract(symbol, underlying, _parse_date(_value(normalized, "expirydate", "expiry")), Decimal(_value(normalized, "strikeprice", "strike").replace(",", "")), option_type)
    except (ValueError, InvalidOperation):
        return None


def _parse_named_future(row: dict[str, str | None]) -> FutureContract | None:
    normalized = {_normalize_header(key): (value or "").strip() for key, value in row.items() if key}
    symbol = _value(normalized, "symbolticker", "symbol")
    underlying = _value(normalized, "underlyingsymbol", "underlying").upper()
    instrument_type = _value(normalized, "optiontype", "instrumenttype", "contracttype").upper()
    if not symbol or underlying != "SENSEX" or (not symbol.upper().endswith("FUT") and "FUT" not in instrument_type):
        return None
    try:
        return FutureContract(symbol, underlying, _parse_date(_value(normalized, "expirydate", "expiry")))
    except ValueError:
        return None


def _normalize_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def _parse_date(value: str) -> date:
    for pattern in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError
