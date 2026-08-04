from __future__ import annotations

from datetime import date
from pathlib import Path

from sensex_chain.instruments import FyersInstrumentCatalog, chunk_subscriptions


def catalog() -> FyersInstrumentCatalog:
    contents = (Path(__file__).parent / "fixtures" / "bse_fo_sample.csv").read_text(encoding="utf-8")
    return FyersInstrumentCatalog.from_csv(contents)


def test_selects_nearest_expiry_with_both_call_and_put() -> None:
    chain = catalog().current_sensex_chain(date(2026, 8, 4))

    assert chain.expiry == date(2026, 8, 6)
    assert {contract.option_type for contract in chain.contracts} == {"CE", "PE"}
    assert chain.symbols[0] == "BSE:SENSEX-INDEX"


def test_uses_next_expiry_from_master_when_nearest_has_expired() -> None:
    chain = catalog().current_sensex_chain(date(2026, 8, 12))

    assert chain.expiry == date(2026, 8, 13)


def test_chunks_401_symbols_into_200_200_1() -> None:
    chunks = chunk_subscriptions([f"BSE:X{number}" for number in range(401)])

    assert [len(chunk) for chunk in chunks] == [200, 200, 1]
