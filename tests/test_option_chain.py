from __future__ import annotations

from sensex_chain.option_chain import extract_option_ticks


def test_extract_option_ticks_reads_oi_change_and_greeks_from_fyers_option_chain() -> None:
    response = {
        "s": "ok",
        "data": {
            "optionsChain": [
                {
                    "symbol": "BSE:SENSEX26AUG80000CE",
                    "ltp": 125.5,
                    "oi": 400.0,
                    "oich": 25.0,
                    "greeks": {"iv": 16.2, "delta": 0.51, "gamma": 0.001, "theta": -12.3, "vega": 8.7, "rho": 1.2},
                },
                {"symbol": "BSE:SENSEX26AUG80000PE", "oi": 450.0, "oich": -10.0},
            ]
        },
    }

    ticks = extract_option_ticks(response, {"BSE:SENSEX26AUG80000CE", "BSE:SENSEX26AUG80000PE"})

    assert ticks["BSE:SENSEX26AUG80000CE"] == {
        "symbol": "BSE:SENSEX26AUG80000CE",
        "ltp": 125.5,
        "oi": 400.0,
        "oi_change": 25.0,
        "iv": 16.2,
        "delta": 0.51,
        "gamma": 0.001,
        "theta": -12.3,
        "vega": 8.7,
        "rho": 1.2,
    }
    assert ticks["BSE:SENSEX26AUG80000PE"]["oi"] == 450.0
    assert ticks["BSE:SENSEX26AUG80000PE"]["oi_change"] == -10.0

class RecordingModel:
    def __init__(self) -> None:
        self.request = None

    def optionchain(self, *, data):
        self.request = data
        return {
            "s": "ok",
            "data": {"optionsChain": [{"symbol": "BSE:SENSEX26AUG80000CE", "oi": 400, "oich": 25, "greeks": {"iv": 16.2, "delta": 0.51}}]},
        }


def test_fyers_option_chain_enricher_requests_current_chain_with_greeks_and_updates_cache() -> None:
    from datetime import datetime
    from sensex_chain.cache import LatestMarketCache
    from sensex_chain.option_chain import FyersOptionChainEnricher
    from sensex_chain.timebox import KOLKATA
    from test_cache import chain

    model = RecordingModel()
    cache = LatestMarketCache()
    enricher = FyersOptionChainEnricher("client-id", "token", model_factory=lambda client_id, token: model)

    enricher.refresh(chain(), cache)

    assert model.request == {"symbol": "BSE:SENSEX-INDEX", "strikecount": 1, "timestamp": "", "greeks": "1"}
    assert enricher.diagnostic_code == "OPTION_CHAIN_OK"
    row = cache.snapshot(chain(), datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)).rows[0]
    assert row.call.oi == 400
    assert row.call.iv == 16.2


def test_fyers_option_chain_enricher_backs_off_without_repeating_a_429_request() -> None:
    from sensex_chain.cache import LatestMarketCache
    from sensex_chain.option_chain import FyersOptionChainEnricher
    from sensex_chain.rate_limit import FyersRequestGate
    from test_cache import chain

    class RateLimitedModel:
        calls = 0

        def optionchain(self, *, data):
            self.calls += 1
            return {"s": "error", "code": 429, "message": "request limit reached"}

    now = [0.0]
    model = RateLimitedModel()
    enricher = FyersOptionChainEnricher("client-id", "token", model_factory=lambda client_id, token: model, request_gate=FyersRequestGate(monotonic=lambda: now[0]))

    enricher.refresh(chain(), LatestMarketCache())
    enricher.refresh(chain(), LatestMarketCache())

    assert model.calls == 1
    assert enricher.diagnostic_code == "RATE_LIMIT_BACKOFF_30S"


def test_strike_count_covers_every_strike_in_the_selected_expiry() -> None:
    from datetime import date
    from decimal import Decimal
    from sensex_chain.instruments import CurrentExpiryChain, OptionContract
    from sensex_chain.option_chain import _strike_count

    chain = CurrentExpiryChain(
        date(2026, 8, 6),
        tuple(
            OptionContract(f"BSE:SENSEX26AUG{strike}{option_type}", "SENSEX", date(2026, 8, 6), Decimal(str(strike)), option_type)
            for strike in (80000, 80100, 80200)
            for option_type in ("CE", "PE")
        ),
    )

    assert _strike_count(chain) == 3
