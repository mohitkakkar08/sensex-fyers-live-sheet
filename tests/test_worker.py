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

    def write_snapshot(self, snapshot, status) -> None:
        self.writes += 1


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
