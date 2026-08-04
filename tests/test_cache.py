from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sensex_chain.cache import LatestMarketCache
from sensex_chain.instruments import CurrentExpiryChain, FutureContract, OptionContract
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


def test_current_expiry_chain_reuses_option_symbols_and_strike_pairs() -> None:
    current = chain()

    assert current.option_symbols == frozenset({"BSE:SENSEX26AUG80000CE", "BSE:SENSEX26AUG80000PE"})
    assert current.strike_pairs == ((Decimal("80000"), current.contracts[0], current.contracts[1]),)



def test_snapshot_includes_the_latest_sensex_future_tick() -> None:
    current = CurrentExpiryChain(
        expiry=date(2026, 8, 6),
        contracts=chain().contracts,
        future=FutureContract("BSE:SENSEX26AUGFUT", "SENSEX", date(2026, 8, 27)),
    )
    cache = LatestMarketCache()
    cache.upsert({"symbol": "BSE:SENSEX26AUGFUT", "ltp": 78500, "oi": 125000, "oi_change": 4500, "vol_traded_today": 42000, "avg_trade_price": 78475})

    snapshot = cache.snapshot(current, datetime(2026, 8, 5, 9, 15, tzinfo=KOLKATA))

    assert snapshot.future is not None
    assert snapshot.future.symbol == "BSE:SENSEX26AUGFUT"
    assert snapshot.future.oi == 125000
    assert snapshot.future.vwap == 78475
