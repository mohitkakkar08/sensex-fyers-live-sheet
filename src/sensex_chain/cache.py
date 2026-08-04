"""Thread-safe latest-value cache and complete option-chain snapshots."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import Lock
from typing import Mapping
from .instruments import CurrentExpiryChain, INDIA_VIX_SYMBOL, INDEX_SYMBOL, OptionContract

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
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None

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
    india_vix: MarketTick
    rows: tuple[ChainRow, ...]

@dataclass(frozen=True)
class MarketDataCoverage:
    tick_count: int
    option_tick_count: int
    has_underlying_tick: bool

class LatestMarketCache:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ticks: dict[str, MarketTick] = {}
    def upsert(self, raw_tick: Mapping[str, object]) -> None:
        tick = normalize_tick(raw_tick)
        if tick is None: return
        with self._lock:
            previous = self._ticks.get(tick.symbol)
            self._ticks[tick.symbol] = tick if previous is None else _merge_tick(previous, tick)
    def coverage(self, chain: CurrentExpiryChain) -> MarketDataCoverage:
        with self._lock: symbols=set(self._ticks)
        option_symbols=chain.option_symbols
        return MarketDataCoverage(len(symbols),len(symbols & option_symbols),INDEX_SYMBOL in symbols)
    def snapshot(self, chain: CurrentExpiryChain, now: datetime) -> ChainSnapshot:
        with self._lock: ticks=dict(self._ticks)
        rows = tuple(
            ChainRow(
                strike,
                ticks.get(call.symbol, MarketTick(call.symbol)),
                ticks.get(put.symbol, MarketTick(put.symbol)),
            )
            for strike, call, put in chain.strike_pairs
        )
        return ChainSnapshot(chain.expiry,now,ticks.get(INDEX_SYMBOL,MarketTick(INDEX_SYMBOL)),ticks.get(INDIA_VIX_SYMBOL,MarketTick(INDIA_VIX_SYMBOL)),rows)

def normalize_tick(raw_tick: Mapping[str, object]) -> MarketTick | None:
    symbol=str(raw_tick.get('symbol') or raw_tick.get('symbol_name') or '').strip(); ltp=_number(raw_tick,'ltp','lp')
    if not symbol or (raw_tick.get('ltp') is not None and ltp is None): return None
    return MarketTick(symbol,ltp,_number(raw_tick,'prev_close_price','prev_close'),_number(raw_tick,'open_price','open'),_number(raw_tick,'high_price','high'),_number(raw_tick,'low_price','low'),_number(raw_tick,'vol_traded_today','volume'),_number(raw_tick,'oi','OI','open_interest'),_number(raw_tick,'oi_change','OIch','oich','change_in_oi'),_number(raw_tick,'avg_trade_price','vwap'),_number(raw_tick,'iv','implied_volatility'),_number(raw_tick,'delta'),_number(raw_tick,'gamma'),_number(raw_tick,'theta'),_number(raw_tick,'vega'),_number(raw_tick,'rho'))
def _number(raw_tick: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        if key in raw_tick and raw_tick[key] not in (None,''):
            try: return float(raw_tick[key])
            except (TypeError,ValueError): return None
    return None

def _merge_tick(previous: MarketTick, update: MarketTick) -> MarketTick:
    values = {field: getattr(update, field) if getattr(update, field) is not None else getattr(previous, field) for field in MarketTick.__dataclass_fields__}
    return MarketTick(**values)
