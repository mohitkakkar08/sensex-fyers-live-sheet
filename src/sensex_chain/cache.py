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
        with self._lock: self._ticks[tick.symbol] = tick
    def coverage(self, chain: CurrentExpiryChain) -> MarketDataCoverage:
        with self._lock: symbols=set(self._ticks)
        option_symbols={c.symbol for c in chain.contracts}
        return MarketDataCoverage(len(symbols),len(symbols & option_symbols),INDEX_SYMBOL in symbols)
    def snapshot(self, chain: CurrentExpiryChain, now: datetime) -> ChainSnapshot:
        with self._lock: ticks=dict(self._ticks)
        by_strike: dict[Decimal,dict[str,OptionContract]]={}
        for c in chain.contracts: by_strike.setdefault(c.strike,{})[c.option_type]=c
        rows=tuple(ChainRow(strike,ticks.get(contracts['CE'].symbol,MarketTick(contracts['CE'].symbol)),ticks.get(contracts['PE'].symbol,MarketTick(contracts['PE'].symbol))) for strike,contracts in sorted(by_strike.items()) if 'CE' in contracts and 'PE' in contracts)
        return ChainSnapshot(chain.expiry,now,ticks.get(INDEX_SYMBOL,MarketTick(INDEX_SYMBOL)),ticks.get(INDIA_VIX_SYMBOL,MarketTick(INDIA_VIX_SYMBOL)),rows)

def normalize_tick(raw_tick: Mapping[str, object]) -> MarketTick | None:
    symbol=str(raw_tick.get('symbol') or raw_tick.get('symbol_name') or '').strip(); ltp=_number(raw_tick,'ltp','lp')
    if not symbol or (raw_tick.get('ltp') is not None and ltp is None): return None
    return MarketTick(symbol,ltp,_number(raw_tick,'prev_close_price','prev_close'),_number(raw_tick,'open_price','open'),_number(raw_tick,'high_price','high'),_number(raw_tick,'low_price','low'),_number(raw_tick,'vol_traded_today','volume'),_number(raw_tick,'oi','OI'),_number(raw_tick,'oi_change','OIch'),_number(raw_tick,'avg_trade_price','vwap'))
def _number(raw_tick: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        if key in raw_tick and raw_tick[key] not in (None,''):
            try: return float(raw_tick[key])
            except (TypeError,ValueError): return None
    return None
