"""FYERS BSE derivatives-master parsing and current-expiry selection."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence


INSTRUMENT_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"
INDEX_SYMBOL = "BSE:SENSEX-INDEX"


class InstrumentDiscoveryError(ValueError):
    """Raised if an instrument master cannot yield a safe SENSEX chain."""


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str


@dataclass(frozen=True)
class CurrentExpiryChain:
    expiry: date
    contracts: tuple[OptionContract, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return (INDEX_SYMBOL,) + tuple(contract.symbol for contract in self.contracts)


class FyersInstrumentCatalog:
    """A validated, in-memory view of FYERS' BSE F&O symbol master."""

    def __init__(self, contracts: Iterable[OptionContract]) -> None:
        self._contracts = tuple(contracts)

    @classmethod
    def from_csv(cls, contents: str) -> "FyersInstrumentCatalog":
        reader = csv.DictReader(io.StringIO(contents))
        if not reader.fieldnames:
            raise InstrumentDiscoveryError("BSE_FO.csv has no header row")
        contracts: list[OptionContract] = []
        for row in reader:
            contract = _parse_contract(row)
            if contract is not None:
                contracts.append(contract)
        return cls(contracts)

    @classmethod
    def download(cls, http: object) -> "FyersInstrumentCatalog":
        response = http.get(INSTRUMENT_MASTER_URL, timeout=30)
        response.raise_for_status()
        return cls.from_csv(response.text)
    def current_sensex_chain(self, today: date) -> CurrentExpiryChain:
        candidates = [
            contract
            for contract in self._contracts
            if contract.underlying == "SENSEX" and contract.expiry >= today
        ]
        for expiry in sorted({contract.expiry for contract in candidates}):
            contracts = tuple(
                sorted(
                    (contract for contract in candidates if contract.expiry == expiry),
                    key=lambda contract: (contract.strike, contract.option_type, contract.symbol),
                )
            )
            types = {contract.option_type for contract in contracts}
            if {"CE", "PE"}.issubset(types):
                return CurrentExpiryChain(expiry=expiry, contracts=contracts)
        raise InstrumentDiscoveryError(
            "No current or future BSE SENSEX CE/PE expiry was found in BSE_FO.csv"
        )


def chunk_subscriptions(symbols: Sequence[str], max_symbols: int = 200) -> list[list[str]]:
    """Return stable subscription chunks within the FYERS DataSocket limit."""

    if max_symbols < 1:
        raise ValueError("max_symbols must be positive")
    return [list(symbols[start : start + max_symbols]) for start in range(0, len(symbols), max_symbols)]


def _parse_contract(row: dict[str, str | None]) -> OptionContract | None:
    normalized = {_normalize_header(name): (value or "").strip() for name, value in row.items() if name}
    symbol = _value(normalized, "symbolticker", "symbol")
    underlying = _value(normalized, "underlyingsymbol", "underlying").upper()
    option_type = _value(normalized, "optiontype").upper()
    expiry_value = _value(normalized, "expirydate", "expiry")
    strike_value = _value(normalized, "strikeprice", "strike")
    if not symbol or underlying != "SENSEX" or option_type not in {"CE", "PE"}:
        return None
    try:
        expiry = _parse_date(expiry_value)
        strike = Decimal(strike_value.replace(",", ""))
    except (ValueError, InvalidOperation):
        return None
    return OptionContract(symbol=symbol, underlying=underlying, expiry=expiry, strike=strike, option_type=option_type)


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
            continue
    raise ValueError(f"Unsupported expiry date: {value}")
