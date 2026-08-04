"""Thread-safe latest-value cache and complete option-chain snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import Lock
from typing import Mapping

from .instruments import CurrentExpiryChain, INDEX_SYMBOL, OptionContract


@dataclass(frozen=True)
class MarketTick:
    symbol: str
    ltp: float | None = None
    prev_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    oi: float | None = None
    oi_change: float | None = None
    vwap: float | None = None


@dataclass(frozen=True)
class ChainRow:
    strike: Decimal
    call: MarketTick
    put: MarketTick


@dataclass(frozen=True)
class ChainSnapshot:
    expiry: datetime | object
    updated_at: datetime
    underlying: MarketTick
    rows: tuple[ChainRow, ...]


@dataclass(frozen=True)
class MarketDataCoverage:
    tick_count: int
    option_tick_count: int
    has_underlying_tick: bool


class LatestMarketCache:
    """Stores the latest valid payload per subscribed symbol."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ticks: dict[str, MarketTick] = {}

    def upsert(self, raw_tick: Mapping[str, object]) -> None:
        tick = normalize_tick(raw_tick)
        if tick is None:
            return
        with self._lock:
            self._ticks[tick.symbol] = tick

    def coverage(self, chain: CurrentExpiryChain) -> MarketDataCoverage:
        with self._lock:
            symbols = set(self._ticks)
        option_symbols = {contract.symbol for contract in chain.contracts}
        return MarketDataCoverage(
            tick_count=len(symbols),
            option_tick_count=len(symbols & option_symbols),
            has_underlying_tick=INDEX_SYMBOL in symbols,
        )

    def snapshot(self, chain: CurrentExpiryChain, now: datetime) -> ChainSnapshot:
        with self._lock:
            ticks = dict(self._ticks)
        contracts_by_strike: dict[Decimal, dict[str, OptionContract]] = {}
        for contract in chain.contracts:
            contracts_by_strike.setdefault(contract.strike, {})[contract.option_type] = contract
        rows = tuple(
            ChainRow(
                strike=strike,
                call=ticks.get(contracts["CE"].symbol, MarketTick(contracts["CE"].symbol)),
                put=ticks.get(contracts["PE"].symbol, MarketTick(contracts["PE"].symbol)),
            )
            for strike, contracts in sorted(contracts_by_strike.items())
            if "CE" in contracts and "PE" in contracts
        )
        return ChainSnapshot(
            expiry=chain.expiry,
            updated_at=now,
            underlying=ticks.get(INDEX_SYMBOL, MarketTick(INDEX_SYMBOL)),
            rows=rows,
        )


def normalize_tick(raw_tick: Mapping[str, object]) -> MarketTick | None:
    symbol = str(raw_tick.get("symbol") or raw_tick.get("symbol_name") or "").strip()
    ltp = _number(raw_tick, "ltp", "lp")
    if not symbol or (raw_tick.get("ltp") is not None and ltp is None):
        return None
    return MarketTick(
        symbol=symbol,
        ltp=ltp,
        prev_close=_number(raw_tick, "prev_close_price", "prev_close"),
        open=_number(raw_tick, "open_price", "open"),
        high=_number(raw_tick, "high_price", "high"),
        low=_number(raw_tick, "low_price", "low"),
        volume=_number(raw_tick, "vol_traded_today", "volume"),
        oi=_number(raw_tick, "oi", "OI"),
        oi_change=_number(raw_tick, "oi_change", "OIch"),
        vwap=_number(raw_tick, "avg_trade_price", "vwap"),
    )


def _number(raw_tick: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        if key in raw_tick and raw_tick[key] not in (None, ""):
            try:
                return float(raw_tick[key])
            except (TypeError, ValueError):
                return None
    return None
