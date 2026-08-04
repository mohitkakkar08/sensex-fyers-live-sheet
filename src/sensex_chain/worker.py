"""Supervisor that streams one SENSEX expiry until its market-time boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain, FyersInstrumentCatalog, chunk_subscriptions
from .sheet import WorkerStatus
from .timebox import SessionSegment, seconds_remaining


class Clock(Protocol):
    def now(self): ...

    def sleep(self, seconds: float) -> None: ...


class TokenProvider(Protocol):
    def access_token(self) -> str: ...


class DataFeed(Protocol):
    def start(self, symbols, on_tick) -> None: ...

    def stop(self) -> None: ...


class SheetGateway(Protocol):
    def write_snapshot(self, snapshot, status: WorkerStatus) -> None: ...


class LiveChainWorker:
    """Coordinates only market data and batch sheet writes."""

    def __init__(
        self,
        catalog: FyersInstrumentCatalog,
        token_provider: TokenProvider,
        feed_factory: Callable[[str], DataFeed],
        cache: LatestMarketCache,
        gateway: SheetGateway,
        clock: Clock,
        flush_seconds: int,
    ) -> None:
        self._catalog = catalog
        self._token_provider = token_provider
        self._feed_factory = feed_factory
        self._cache = cache
        self._gateway = gateway
        self._clock = clock
        self._flush_seconds = flush_seconds

    def run(self, segment: SessionSegment, max_cycles: int | None = None) -> int:
        now = self._clock.now()
        if seconds_remaining(now, segment) <= 0:
            return 0
        chain: CurrentExpiryChain = self._catalog.current_sensex_chain(now.date())
        token = self._token_provider.access_token()
        feeds = []
        try:
            for symbols in chunk_subscriptions(chain.symbols):
                feed = self._feed_factory(token)
                feed.start(symbols, self._cache.upsert)
                feeds.append(feed)
            cycles = 0
            while seconds_remaining(self._clock.now(), segment) > 0:
                current = self._clock.now()
                self._gateway.write_snapshot(
                    self._cache.snapshot(chain, current), WorkerStatus.connected(current)
                )
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                self._clock.sleep(min(self._flush_seconds, seconds_remaining(current, segment)))
            return 0
        finally:
            for feed in feeds:
                feed.stop()
