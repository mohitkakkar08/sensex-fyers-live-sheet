"""Supervisor that streams one SENSEX expiry until its market-time boundary."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain, FyersInstrumentCatalog
from .sheet import SheetGatewayError, WorkerStatus
from .timebox import SessionSegment, seconds_remaining


class Clock(Protocol):
    def now(self): ...
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class TokenProvider(Protocol):
    def access_token(self) -> str: ...


class DataFeed(Protocol):
    def start(self, symbols, on_tick) -> None: ...
    def stop(self) -> None: ...


class SheetGateway(Protocol):
    def write_snapshot(self, snapshot, status: WorkerStatus) -> None: ...


class OptionChainEnricher(Protocol):
    diagnostic_code: str
    def refresh(self, chain: CurrentExpiryChain, cache: LatestMarketCache) -> None: ...


class LiveChainWorker:
    def __init__(self, catalog: FyersInstrumentCatalog, token_provider: TokenProvider, feed_factory: Callable[[str], DataFeed], cache: LatestMarketCache, gateway: SheetGateway, clock: Clock, flush_seconds: int, option_chain_factory: Callable[[str], OptionChainEnricher] | None = None) -> None:
        self._catalog = catalog
        self._token_provider = token_provider
        self._feed_factory = feed_factory
        self._cache = cache
        self._gateway = gateway
        self._clock = clock
        self._flush_seconds = flush_seconds
        self._option_chain_factory = option_chain_factory

    def run(self, segment: SessionSegment, max_cycles: int | None = None) -> int:
        now = self._clock.now()
        if seconds_remaining(now, segment) <= 0:
            return 0
        chain: CurrentExpiryChain = self._catalog.current_sensex_chain(now.date())
        token = self._token_provider.access_token()
        feeds: list[DataFeed] = []
        option_chain = self._option_chain_factory(token) if self._option_chain_factory else None
        next_flush_at = self._clock.monotonic()
        try:
            feed = self._feed_factory(token)
            feed.start(chain.symbols, self._cache.upsert)
            feeds.append(feed)
            cycles = 0
            while seconds_remaining(self._clock.now(), segment) > 0:
                current = self._clock.now()
                option_chain_diagnostic = "OPTION_CHAIN_DISABLED"
                if option_chain is not None:
                    option_chain.refresh(chain, self._cache)
                    option_chain_diagnostic = getattr(option_chain, "diagnostic_code", "OPTION_CHAIN_OK")
                try:
                    self._gateway.write_snapshot(self._cache.snapshot(chain, current), self._status(chain, current, feeds, option_chain_diagnostic))
                except SheetGatewayError:
                    next_flush_at = self._sleep_until_next_flush(next_flush_at, segment)
                    continue
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                next_flush_at = self._sleep_until_next_flush(next_flush_at, segment)
            return 0
        finally:
            for feed in feeds:
                feed.stop()

    def _sleep_until_next_flush(self, previous_flush_at: float, segment: SessionSegment) -> float:
        deadline = previous_flush_at + self._flush_seconds
        current_monotonic = self._clock.monotonic()
        while deadline <= current_monotonic:
            deadline += self._flush_seconds
        delay = min(deadline - current_monotonic, seconds_remaining(self._clock.now(), segment))
        if delay > 0:
            self._clock.sleep(delay)
        return deadline

    def _status(self, chain: CurrentExpiryChain, now, feeds: list[DataFeed], option_chain_diagnostic: str) -> WorkerStatus:
        coverage = self._cache.coverage(chain)
        socket_error = next((getattr(feed, "diagnostic_code") for feed in feeds if getattr(feed, "diagnostic_code", "") in {"SOCKET_RUNTIME_ERROR", "SOCKET_START_FAILED", "SOCKET_CLOSED"}), None)
        if socket_error:
            return WorkerStatus("PARTIAL_LIVE", now, socket_error, coverage.tick_count, coverage.option_tick_count)
        if coverage.tick_count == 0:
            return WorkerStatus.waiting_for_ticks(now, "SOCKET_SUBSCRIBED_NO_TICKS")
        if not coverage.has_underlying_tick or coverage.option_tick_count == 0:
            return WorkerStatus.partial_live(now, coverage.tick_count, coverage.option_tick_count)
        if option_chain_diagnostic not in {"OPTION_CHAIN_OK", "OPTION_CHAIN_DISABLED"}:
            return WorkerStatus("PARTIAL_LIVE", now, option_chain_diagnostic, coverage.tick_count, coverage.option_tick_count)
        return WorkerStatus.live(now, coverage.tick_count, coverage.option_tick_count)
