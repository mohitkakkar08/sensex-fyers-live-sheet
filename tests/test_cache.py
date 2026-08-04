from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sensex_chain.cache import LatestMarketCache
from sensex_chain.instruments import CurrentExpiryChain, OptionContract
from sensex_chain.timebox import KOLKATA


def chain() -> CurrentExpiryChain:
    return CurrentExpiryChain(
        expiry=date(2026, 8, 6),
        contracts=(
            OptionContract("BSE:SENSEX26AUG80000CE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "CE"),
            OptionContract("BSE:SENSEX26AUG80000PE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "PE"),
        ),
    )


def test_snapshot_pairs_call_and_put_and_preserves_missing_data_as_none() -> None:
    cache = LatestMarketCache()
    cache.upsert({"symbol": "BSE:SENSEX26AUG80000CE", "ltp": 125.0, "oi": 400})

    row = cache.snapshot(chain(), datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)).rows[0]

    assert row.call.ltp == 125.0
    assert row.put.ltp is None
    assert row.call.oi == 400.0


def test_malformed_tick_does_not_erase_previous_valid_tick() -> None:
    cache = LatestMarketCache()
    valid_tick = {"symbol": "BSE:SENSEX26AUG80000CE", "ltp": 125.0}
    cache.upsert(valid_tick)
    cache.upsert({"symbol": "BSE:SENSEX26AUG80000CE", "ltp": "not-a-number"})

    row = cache.snapshot(chain(), datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)).rows[0]

    assert row.call.ltp == valid_tick["ltp"]
