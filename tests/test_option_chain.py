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

    assert model.request == {"symbol": "BSE:SENSEX-INDEX", "strikecount": 0, "timestamp": "", "greeks": "1"}
    assert enricher.diagnostic_code == "OPTION_CHAIN_OK"
    row = cache.snapshot(chain(), datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)).rows[0]
    assert row.call.oi == 400
    assert row.call.iv == 16.2
