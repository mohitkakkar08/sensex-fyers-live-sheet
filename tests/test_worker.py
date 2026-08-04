from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sensex_chain.cache import LatestMarketCache
from sensex_chain.instruments import CurrentExpiryChain, OptionContract
from sensex_chain.timebox import KOLKATA, SessionSegment
from sensex_chain.worker import LiveChainWorker


class Catalog:
    def current_sensex_chain(self, today: date) -> CurrentExpiryChain:
        return CurrentExpiryChain(
            date(2026, 8, 6),
            (
                OptionContract("BSE:SENSEX26AUG80000CE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "CE"),
                OptionContract("BSE:SENSEX26AUG80000PE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "PE"),
            ),
        )


class TokenProvider:
    def access_token(self) -> str:
        return "token"


class Feed:
    def __init__(self) -> None:
        self.stop_called = False

    def start(self, symbols, on_tick) -> None:
        on_tick({"symbol": "BSE:SENSEX-INDEX", "ltp": 80000})

    def stop(self) -> None:
        self.stop_called = True


class Gateway:
    def __init__(self) -> None:
        self.writes = 0
        self.statuses = []

    def write_snapshot(self, snapshot, status) -> None:
        self.writes += 1
        self.statuses.append(status)


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)

    def sleep(self, seconds: float) -> None:
        assert seconds == 10


def test_worker_writes_snapshot_and_stops_each_feed() -> None:
    feed = Feed()
    gateway = Gateway()
    worker = LiveChainWorker(Catalog(), TokenProvider(), lambda token: feed, LatestMarketCache(), gateway, Clock(), 10)

    assert worker.run(SessionSegment.MORNING, max_cycles=1) == 0
    assert gateway.writes == 1
    assert feed.stop_called is True


class EmptyFeed(Feed):
    def start(self, symbols, on_tick) -> None:
        return None


def test_worker_marks_a_snapshot_waiting_when_no_fyers_tick_arrives() -> None:
    feed = EmptyFeed()
    gateway = Gateway()
    worker = LiveChainWorker(Catalog(), TokenProvider(), lambda token: feed, LatestMarketCache(), gateway, Clock(), 10)

    assert worker.run(SessionSegment.MORNING, max_cycles=1) == 0
    assert gateway.statuses[0].state == "WAITING_FOR_TICKS"
    assert gateway.statuses[0].diagnostic_code == "SOCKET_SUBSCRIBED_NO_TICKS"


class FailedSocketFeed(EmptyFeed):
    diagnostic_code = "SOCKET_RUNTIME_ERROR"


def test_worker_surfaces_a_socket_runtime_diagnostic_before_any_tick_arrives() -> None:
    feed = FailedSocketFeed()
    gateway = Gateway()
    worker = LiveChainWorker(Catalog(), TokenProvider(), lambda token: feed, LatestMarketCache(), gateway, Clock(), 10)

    assert worker.run(SessionSegment.MORNING, max_cycles=1) == 0
    assert gateway.statuses[0].diagnostic_code == "SOCKET_RUNTIME_ERROR"


def test_worker_uses_one_socket_for_a_large_current_expiry_chain() -> None:
    class LargeCatalog:
        def current_sensex_chain(self, today: date) -> CurrentExpiryChain:
            contracts = tuple(
                OptionContract(f"BSE:SENSEX26AUG{70000 + strike}{option_type}", "SENSEX", date(2026, 8, 6), Decimal(70000 + strike), option_type)
                for strike in range(101)
                for option_type in ("CE", "PE")
            )
            return CurrentExpiryChain(date(2026, 8, 6), contracts)

    class RecordingFeed(Feed):
        def __init__(self) -> None:
            super().__init__()
            self.symbols = []

        def start(self, symbols, on_tick) -> None:
            self.symbols = list(symbols)

    feeds = []
    def factory(token):
        feed = RecordingFeed()
        feeds.append(feed)
        return feed

    worker = LiveChainWorker(LargeCatalog(), TokenProvider(), factory, LatestMarketCache(), Gateway(), Clock(), 10)

    assert worker.run(SessionSegment.MORNING, max_cycles=1) == 0
    assert len(feeds) == 1
    assert len(feeds[0].symbols) == 204

class Enricher:
    diagnostic_code = "OPTION_CHAIN_OK"

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, chain, cache) -> None:
        self.calls += 1
        cache.upsert({"symbol": "BSE:SENSEX26AUG80000CE", "oi": 400, "oi_change": 25, "iv": 16.2, "delta": 0.51})


def test_worker_enriches_option_chain_fields_before_writing_snapshot() -> None:
    feed = Feed()
    gateway = Gateway()
    cache = LatestMarketCache()
    enricher = Enricher()
    worker = LiveChainWorker(Catalog(), TokenProvider(), lambda token: feed, cache, gateway, Clock(), 10, option_chain_factory=lambda token: enricher)

    assert worker.run(SessionSegment.MORNING, max_cycles=1) == 0
    assert enricher.calls == 1
    row = cache.snapshot(Catalog().current_sensex_chain(date(2026, 8, 4)), Clock().now()).rows[0]
    assert row.call.oi == 400
    assert row.call.iv == 16.2
