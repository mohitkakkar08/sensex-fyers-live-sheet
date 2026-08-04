from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from sensex_chain.instruments import FutureContract, FyersInstrumentCatalog, INDIA_VIX_SYMBOL, OptionContract, chunk_subscriptions


def catalog() -> FyersInstrumentCatalog:
    contents = (Path(__file__).parent / "fixtures" / "bse_fo_sample.csv").read_text(encoding="utf-8")
    return FyersInstrumentCatalog.from_csv(contents)


def test_selects_nearest_expiry_with_both_call_and_put() -> None:
    chain = catalog().current_sensex_chain(date(2026, 8, 4))

    assert chain.expiry == date(2026, 8, 6)
    assert {contract.option_type for contract in chain.contracts} == {"CE", "PE"}
    assert chain.symbols[0] == "BSE:SENSEX-INDEX"
    assert chain.symbols[1] == INDIA_VIX_SYMBOL


def test_uses_next_expiry_from_master_when_nearest_has_expired() -> None:
    chain = catalog().current_sensex_chain(date(2026, 8, 12))

    assert chain.expiry == date(2026, 8, 13)


def test_chunks_401_symbols_into_200_200_1() -> None:
    chunks = chunk_subscriptions([f"BSE:X{number}" for number in range(401)])

    assert [len(chunk) for chunk in chunks] == [200, 200, 1]



def test_selects_the_nearest_unexpired_sensex_future_and_subscribes_to_it() -> None:
    catalog = FyersInstrumentCatalog(
        (
            OptionContract("BSE:SENSEX26AUG80000CE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "CE"),
            OptionContract("BSE:SENSEX26AUG80000PE", "SENSEX", date(2026, 8, 6), Decimal("80000"), "PE"),
        ),
        futures=(
            FutureContract("BSE:SENSEX26SEPFUT", "SENSEX", date(2026, 9, 24)),
            FutureContract("BSE:SENSEX26AUGFUT", "SENSEX", date(2026, 8, 27)),
        ),
    )

    chain = catalog.current_sensex_chain(date(2026, 8, 5))

    assert chain.future is not None
    assert chain.future.symbol == "BSE:SENSEX26AUGFUT"
    assert chain.symbols[-1] == "BSE:SENSEX26AUGFUT"



def test_parses_a_positional_fyers_master_future_contract() -> None:
    contents = "\n".join([
        "1211260621000001,SENSEX 06 Aug 26 80000 CE,11,20,0.05,,0915-1540:,2026-08-04,1785983400,BSE:SENSEX26AUG80000CE,12,11,100001,SENSEX,1,-1.0",
        "1211260621000002,SENSEX 06 Aug 26 80000 PE,11,20,0.05,,0915-1540:,2026-08-04,1785983400,BSE:SENSEX26AUG80000PE,12,11,100002,SENSEX,1,-1.0",
        "1211260827825622,SENSEX 27 Aug 26 FUT,11,20,0.05,,0915-1540|1815-1915:,2026-08-04,1787825400,BSE:SENSEX26AUGFUT,12,11,825622,SENSEX,1,-1.0",
    ])

    chain = FyersInstrumentCatalog.from_csv(contents).current_sensex_chain(date(2026, 8, 5))

    assert chain.future is not None
    assert chain.future.symbol == "BSE:SENSEX26AUGFUT"
    assert chain.future.expiry == date(2026, 8, 27)
